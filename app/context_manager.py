from __future__ import annotations
import re
import sqlite3
import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Qualitäts-Gate: triviale Facts ablehnen ────────────────────────────────
# Keys die nie gespeichert werden sollen (Regex auf lowercase key)
_TRIVIAL_KEY_PATTERNS = [
    # Standard-Python-Pakete — kein Discovery-Aufwand nötig
    re.compile(
        r"^pkg_(requests|json|os|sys|re|math|time|datetime|pathlib|subprocess|"
        r"threading|logging|collections|itertools|functools|typing|abc|io|copy|"
        r"shutil|glob|fnmatch|hashlib|base64|urllib|http|email|html|xml|csv|"
        r"sqlite3|random|string|uuid|enum|dataclasses|contextlib|warnings|"
        r"traceback|inspect|operator|struct|array|queue|heapq|bisect|weakref|"
        r"gc|platform|signal|socket|ssl|select|errno|ctypes|unittest|doctest|"
        r"pdb|profile|timeit)$"
    ),
    # Temporäre Job-States (ändern sich pro Job)
    re.compile(r"_(setup_status|needs_setup|step_status|task_status|job_status)$"),
]

# Values die nie gespeichert werden sollen
_TRIVIAL_VALUE_PATTERNS = [
    re.compile(
        r"^(True|False|None|0|1|ok|done|fertig|verfügbar|available|installed|"
        r"not installed|ja|nein|yes|no)$",
        re.IGNORECASE,
    ),
    re.compile(r"ist (verfügbar|installiert|vorhanden|nicht vorhanden|standard)$", re.IGNORECASE),
]


_VALID_FACT_TYPES = {"device", "credential", "path", "api_quirk", "config", "unknown"}

# Typ-abhängige TTLs in Tagen (None = nie löschen)
_TYPE_TTL_DAYS: Dict[str, Optional[int]] = {
    "credential": None,
    "device":     None,
    "path":       180,
    "api_quirk":  180,
    "config":     365,
    "unknown":    60,
}


def _is_trivial_fact(key: str, value: str) -> bool:
    """Gibt True zurück wenn der Fakt zu trivial ist um gespeichert zu werden."""
    k = str(key or "").strip().lower()
    v = str(value or "").strip()
    for p in _TRIVIAL_KEY_PATTERNS:
        if p.search(k):
            return True
    for p in _TRIVIAL_VALUE_PATTERNS:
        if p.search(v):
            return True
    # Zu kurz/nichtssagend
    if len(v) < 10:
        return True
    return False

class ContextManager:
    """
    Zentrale Instanz für die State-Verwaltung (V3).
    Nutzt SQLite für persistente Fakten (Single Source of Truth)
    und ChromaDB für semantische Fact-Suche (ChatGPT-Style).

    OPT-2: Persistente SQLite-Connection mit RLock.
    OPT-12: TTL-Cache für get_pinned_context() – max 30s gültig.
    """
    _PINNED_CACHE_TTL = 30.0  # Sekunden

    def __init__(self, db_path: str = "data/task_state.db", workspace_dir: str = "data/workspace"):
        self.db_path = Path(db_path)
        self.workspace = Path(workspace_dir)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.plan_file = self.workspace / "plan.md"
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        # TTL-Cache für get_pinned_context()
        self._pinned_cache: Optional[Tuple[float, str]] = None
        # ChromaDB-Instanz (lazy init, None wenn nicht verfügbar)
        self._chroma: Any = None
        self._chroma_init_attempted = False
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Gibt die persistente Verbindung zurück (lazy-init, thread-safe via RLock)."""
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=10,
                )
            return self._conn

    def _init_db(self):
        """Initialisiert die Facts-Tabelle in der SQLite-Datenbank."""
        with self._lock:
            conn = self._get_conn()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS discovered_facts (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    type TEXT DEFAULT 'unknown',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            # Rückwärtskompatibilität: type-Spalte nachrüsten falls Tabelle alt
            try:
                conn.execute("ALTER TABLE discovered_facts ADD COLUMN type TEXT DEFAULT 'unknown'")
                conn.commit()
            except Exception:
                pass  # Spalte existiert bereits

    def _invalidate_pinned_cache(self) -> None:
        """Invalidiert den TTL-Cache nach Plan/Fact-Änderungen."""
        self._pinned_cache = None

    # ── ChromaDB: Semantische Fact-Suche (ChatGPT-Style) ─────────────────────

    def _get_chroma(self):
        """Lazy-Init der ChromaDB-Instanz. Gibt None zurück wenn nicht verfügbar."""
        if self._chroma_init_attempted:
            return self._chroma
        self._chroma_init_attempted = True
        try:
            from app.chroma_memory import ChromaMemoryStore
            chroma_path = self.db_path.parent / "chroma_db"
            self._chroma = ChromaMemoryStore(db_path=chroma_path, collection_name="facts")
            # Bestehende SQLite-Facts in ChromaDB migrieren (einmalig bei erster Nutzung)
            self._migrate_facts_to_chroma()
        except Exception:
            self._chroma = None
        return self._chroma

    def _migrate_facts_to_chroma(self) -> None:
        """Migriert vorhandene SQLite-Facts in ChromaDB (falls noch nicht indiziert)."""
        if self._chroma is None:
            return
        try:
            all_facts = self.read_facts_with_meta()
            for key, meta in all_facts.items():
                value = meta.get("value", "")
                self._chroma.upsert_memory(
                    "fact", key,
                    {"info": f"{key}: {value}"},
                    confidence=1.0,
                    collection_name="fact",
                )
        except Exception:
            pass

    def retrieve_relevant_facts(
        self, query: str, top_k: int = 8, fact_type: Optional[str] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Semantisches Fact-Retrieval (ChatGPT-Style):
        1. Optionaler Typ-Filter (reduziert Suchraum vor Embedding-Suche)
        2. ChromaDB Embedding-Suche (all-MiniLM-L6-v2)
        3. Fallback: neueste top_k Fakten wenn ChromaDB nicht verfügbar
        """
        all_facts = self.read_facts_with_meta()
        if not all_facts:
            return {}

        # Typ-Filter: nur Facts des gesuchten Typs berücksichtigen
        if fact_type and fact_type in _VALID_FACT_TYPES:
            all_facts = {k: v for k, v in all_facts.items() if v.get("type") == fact_type}
            if not all_facts:
                return {}

        # Primär: ChromaDB semantische Suche
        chroma = self._get_chroma()
        if chroma is not None and not getattr(chroma, "_fallback_active", True):
            try:
                results = chroma.search(query, limit=top_k, collection_name="fact")
                if results:
                    matched: Dict[str, Dict[str, str]] = {}
                    for r in results:
                        key = r.get("key")
                        if key and key in all_facts:
                            matched[key] = all_facts[key]
                    if matched:
                        return matched
            except Exception:
                pass

        # Fallback: neueste top_k Fakten (immer etwas anzeigen)
        sorted_by_time = sorted(
            all_facts.items(),
            key=lambda kv: kv[1].get("timestamp", ""),
            reverse=True,
        )
        return {k: v for k, v in sorted_by_time[:top_k]}

    def get_pinned_context(self) -> str:
        """
        Generiert den Context-Block für den System-Prompt (Plan + Fakten-Übersicht).
        OPT-12: Gecacht für _PINNED_CACHE_TTL Sekunden.
        Relevante Fakten werden separat via BM25 direkt an die Aufgabe injiziert.
        """
        now = time.monotonic()
        with self._lock:
            if self._pinned_cache is not None:
                cached_ts, cached_val = self._pinned_cache
                if (now - cached_ts) < self._PINNED_CACHE_TTL:
                    return cached_val
        # Cache miss oder abgelaufen – neu aufbauen
        result = self._build_pinned_context()
        with self._lock:
            self._pinned_cache = (now, result)
        return result

    def _build_pinned_context(self) -> str:
        plan = self.read_plan()
        n_facts = self._count_facts()

        facts_hint = (
            f"Gespeicherte Fakten: {n_facts} (relevante wurden direkt zur Aufgabe injiziert; "
            "alle via mem_get_facts() abrufbar, löschen via mem_delete_fact(key))."
            if n_facts > 0 else
            "Keine Fakten gespeichert. Nach erfolgreichen Jobs mem_save_fact aufrufen."
        )

        # 🚨 AGGRESSIVE: Warnung wenn Dateien im Plan vorhanden sind
        has_files = "📁 Datei erstellt" in plan or "DATEI ERSTELLT" in plan
        file_warning = (
            "\n⚠️ WICHTIG: DATEIEN IM PLAN GEFUNDEN!\n"
            "   Du MUSST diese Dateien sofort nutzen in DIESEM Schritt!\n"
            "   NICHT ignorieren und was anderes machen!\n"
            if has_files else ""
        )

        return (
            "### 📍 PINNED CONTEXT (Aktueller System-State)\n"
            f"🚨 DIESER PLAN MUSS ABGEARBEITET WERDEN - LIES IHN GENAU:\n{plan}\n"
            f"{file_warning}\n"
            f"{facts_hint}\n"
        )

    def _count_facts(self) -> int:
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute("SELECT COUNT(*) FROM discovered_facts").fetchone()
                return row[0] if row else 0
            except Exception:
                return 0

    def read_plan(self) -> str:
        if not self.plan_file.exists():
            return "Noch kein aktiver Plan vorhanden. Erstelle einen mit mem_update_plan."
        return self.plan_file.read_text(encoding="utf-8")

    def update_plan(self, content: str) -> str:
        try:
            self.plan_file.write_text(content, encoding="utf-8")
            self._invalidate_pinned_cache()  # OPT-12: Cache invalidieren
            return f"Plan erfolgreich aktualisiert: {self.plan_file}"
        except Exception as e:
            return f"ERROR beim Plan-Update: {e}"

    def read_facts(self) -> Dict[str, str]:
        """Liest alle Fakten als {key: value} – für Rückwärtskompatibilität."""
        with self._lock:
            try:
                conn = self._get_conn()
                cursor = conn.execute("SELECT key, value FROM discovered_facts")
                return {row[0]: row[1] for row in cursor.fetchall()}
            except Exception:
                return {}

    def read_facts_with_meta(self) -> Dict[str, Dict[str, str]]:
        """Liest alle Fakten mit Typ und Zeitstempel: {key: {value, type, timestamp}}."""
        with self._lock:
            try:
                conn = self._get_conn()
                cursor = conn.execute(
                    "SELECT key, value, type, timestamp FROM discovered_facts ORDER BY timestamp DESC"
                )
                return {
                    row[0]: {"value": row[1], "type": row[2] or "unknown", "timestamp": row[3]}
                    for row in cursor.fetchall()
                }
            except Exception:
                return {}

    def save_fact(self, key: str, value: str, _bypass: bool = False, fact_type: str = "unknown") -> str:
        """Speichert einen Fakt in der SQLite-Datenbank (Upsert).
        _bypass=True: Qualitäts-Gate überspringen (nur für interne System-Calls).
        fact_type: device | credential | path | api_quirk | config | unknown
        """
        key = str(key or "").strip()
        value = str(value or "").strip()
        fact_type = str(fact_type or "unknown").strip()
        if fact_type not in _VALID_FACT_TYPES:
            fact_type = "unknown"
        # Qualitäts-Gate: triviale Facts ablehnen
        if not _bypass and _is_trivial_fact(key, value):
            return f"Fakt nicht gespeichert (trivial/nicht speichernswert): {key}"
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO discovered_facts (key, value, type, timestamp) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (key, value, fact_type)
                )
                conn.commit()
                self._invalidate_pinned_cache()
                # Auch in ChromaDB indexieren für semantische Suche
                try:
                    chroma = self._get_chroma()
                    if chroma is not None:
                        chroma.upsert_memory(
                            "fact", key,
                            {"info": f"{key}: {value}", "fact_type": fact_type},
                            confidence=1.0,
                            collection_name="fact",
                        )
                except Exception:
                    pass
                # Warnung wenn relativer Pfad erkannt — LLM soll korrigieren
                warning = ""
                if ('/' in value or '\\' in value) and not Path(value).is_absolute():
                    try:
                        abs_path = str(Path(value).resolve())
                        warning = f"\nWARNUNG: Relativer Pfad gespeichert. Absoluter Pfad wäre: {abs_path} — bitte mit mem_save_fact korrigieren."
                    except Exception:
                        pass
                return f"Fakt gespeichert [{fact_type}]: {key} = {value}{warning}"
            except Exception as e:
                return f"ERROR beim DB-Speichern: {e}"

    def delete_fact(self, key: str) -> str:
        """Löscht einen veralteten Fakt aus der SQLite-Datenbank."""
        with self._lock:
            try:
                conn = self._get_conn()
                cursor = conn.execute(
                    "DELETE FROM discovered_facts WHERE key = ?", (key,)
                )
                conn.commit()
                self._invalidate_pinned_cache()
                if cursor.rowcount > 0:
                    return f"Fakt gelöscht: {key}"
                else:
                    return f"Fakt nicht gefunden: {key}"
            except Exception as e:
                return f"ERROR beim Löschen: {e}"

    def get_fact(self, key: str) -> Optional[str]:
        """Direktes Key-Lookup ohne semantisches Retrieval. Gibt None zurück wenn nicht vorhanden."""
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT value FROM discovered_facts WHERE key = ?", (key,)
                ).fetchone()
                return row[0] if row else None
            except Exception:
                return None

    def cleanup_old_facts(self, max_age_days: Optional[int] = None) -> int:
        """
        Löscht Facts anhand typ-abhängiger TTLs (credential/device: permanent).
        max_age_days überschreibt den Typ-TTL falls angegeben (nützlich für Tests).
        Gibt Anzahl gelöschter Facts zurück.
        """
        deleted = 0
        with self._lock:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT key, type, timestamp FROM discovered_facts"
                ).fetchall()
                for key, fact_type, ts in rows:
                    k = str(key or "").lower()
                    # System-interne Keys nie löschen
                    if k.startswith("agent_state__") or k.startswith("_"):
                        continue
                    # Typ-TTL bestimmen
                    ttl = _TYPE_TTL_DAYS.get(str(fact_type or "unknown"), 60)
                    if ttl is None:
                        continue  # credential/device: permanent
                    if max_age_days is not None:
                        ttl = min(ttl, max_age_days)
                    cutoff = (datetime.now() - timedelta(days=ttl)).strftime("%Y-%m-%d %H:%M:%S")
                    if str(ts or "") < cutoff:
                        conn.execute("DELETE FROM discovered_facts WHERE key = ?", (key,))
                        deleted += 1
                if deleted:
                    conn.commit()
                    self._invalidate_pinned_cache()
            except Exception:
                pass
        # Auch ChromaDB bereinigen (nutzt eigenen max_age_days-Wert)
        try:
            chroma = self._get_chroma()
            if chroma is not None:
                chroma.cleanup_old_facts(max_age_days=max_age_days or 60)
        except Exception:
            pass
        return deleted

    # ── Agent-Identity Persistence (Phase 2) ─────────────────────

    def save_agent_state(self, dialog_key: str, state: Dict[str, Any]) -> None:
        """Speichert Agent-Identität persistent in discovered_facts (als JSON)."""
        key = f"agent_state__{dialog_key}"
        value = json.dumps(state, ensure_ascii=False, indent=2)
        self.save_fact(key, value, _bypass=True)  # System-intern, kein Qualitäts-Gate

    def load_agent_state(self, dialog_key: str) -> Dict[str, Any]:
        """Lädt Agent-Zustand aus vorherigen Sitzungen."""
        key = f"agent_state__{dialog_key}"
        facts = self.read_facts()
        if key in facts:
            try:
                return json.loads(facts[key])
            except Exception:
                return {}
        return {}

    # ── System-Knowledge Base (Phase 3) ─────────────────────

    def load_system_knowledge(self) -> None:
        """Lädt K.AI Architektur-Wissen einmalig beim Bot-Start in ChromaDB."""
        system_knowledge = [
            {
                "key": "arch_main_py",
                "content": "main.py: ReAct-Loop (Zeile 15678+). Core-File! Braucht Bot-Restart nach Änderung.",
            },
            {
                "key": "arch_tool_registry",
                "content": "tool_registry.py: Registriert alle Tools via ALLOWED_CORE_TOOLS. Neue Tools müssen hier eingetragen werden.",
            },
            {
                "key": "arch_discovered_facts",
                "content": "discovered_facts.db: SQLite mit key/value Pairs. Neue Facts speichert du mit mem_save_fact().",
            },
            {
                "key": "arch_persistent_session",
                "content": "PersistentSession (python_exec.py): Variablen und Imports bleiben zwischen sys_python_exec Calls erhalten.",
            },
            {
                "key": "arch_chromadb",
                "content": "ChromaDB: Semantische Suche. Findet ähnliche Facts automatisch via Embedding-Ähnlichkeit (all-MiniLM-L6-v2).",
            },
            {
                "key": "arch_context_manager",
                "content": "ContextManager: Zentrale State-Verwaltung. retrieve_relevant_facts() wird vor jedem Job aufgerufen.",
            },
            {
                "key": "arch_error_recovery",
                "content": "_error_type_counts: Abbruch nach 3× gleicher Exception. _consecutive_tool_failures: Abbruch nach 3+ Fehlern.",
            },
            {
                "key": "arch_workspace",
                "content": "data/workspace/: Dein Arbeitsbereich für temporäre Dateien. data/chroma_db/: ChromaDB Index.",
            },
        ]

        for item in system_knowledge:
            key = item["key"]
            value = item["content"]
            # Nur laden wenn noch nicht vorhanden
            facts = self.read_facts()
            if key not in facts:
                self.save_fact(key, value, _bypass=True)

    def clear_session_state(self):
        """Setzt den Plan zurück. Facts (Langzeitgedächtnis) bleiben erhalten.

        WICHTIG: discovered_facts sind jobübergreifendes Langzeitgedächtnis und werden
        absichtlich NICHT gelöscht — nur via mem_delete_fact(key) manuell entfernbar.
        """
        if self.plan_file.exists():
            self.plan_file.unlink()
        self._invalidate_pinned_cache()

    def close(self) -> None:
        """Schließt die Datenbankverbindung sauber."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
