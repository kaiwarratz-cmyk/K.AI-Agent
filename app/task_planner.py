"""
Task Planner 2026 – Hierarchical and Agent-led Planning.
Enables decomposition of complex goals into actionable sub-tasks.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT_DIR = Path(__file__).parent.parent
_TEMP_PLAN_DIR = ROOT_DIR / "data" / "plans" / "temp"

# ---------------------------------------------------------------------------
# Komplexitätserkennung
# ---------------------------------------------------------------------------

_COMPLEXITY_KEYWORDS = {
    # Aufwändige Operationen
    "analysiere", "analysier", "analyse", "durchsuche", "durchsuch",
    "erstelle", "erstell", "generiere", "generier", "automatisiere", "automatisier",
    "verarbeite", "verarbeit", "kombiniere", "kombinier", "übertrage", "übertra",
    "synchronisiere", "sync", "konvertiere", "konvertier", "migriere", "migrier",
    # Englisch
    "analyze", "analyse", "search all", "create", "generate", "automate",
    "process", "combine", "transfer", "migrate", "convert", "scrape",
    # Zeitbasiert
    "täglich", "wöchentlich", "stündlich", "every", "schedule", "cron",
    # Multi-Step-Indikatoren
    "dann", "danach", "anschließend", "und speichere", "und schreibe",
    "und sende", "und öffne", "und starte", "und führe",
    "and then", "afterwards", "after that",
}

_SIMPLE_PREFIXES = {
    "was ist", "was sind", "wie ist", "wann ist", "wer ist", "wo ist",
    "erkläre", "erklär", "erklaer", "zeige mir", "zeig mir",
    "what is", "what are", "who is", "when is", "where is", "explain", "show me",
    "hallo", "hi", "danke", "ok", "okay",
}


def should_plan(message: str) -> bool:
    """
    Gibt True zurück wenn die Aufgabe komplex genug für eine temp. Plan-Datei ist.
    Kriterien: Keyword-Treffer ODER geschätzte Action-Anzahl > 1.
    """
    if not message or len(message.strip()) < 10:
        return False

    lower = message.lower().strip()

    # Einfache Anfragen sofort ausschließen
    for prefix in _SIMPLE_PREFIXES:
        if lower.startswith(prefix):
            return False

    # Explizit sehr kurze Nachrichten (<= 4 Wörter) sind meist einfach
    if len(lower.split()) <= 4:
        return False

    # Komplexitäts-Keywords
    for kw in _COMPLEXITY_KEYWORDS:
        if kw in lower:
            return True

    # Mehrere Sätze / Aufzählungen deuten auf Multi-Step hin
    if lower.count("\n") >= 2 or lower.count(",") >= 3:
        return True

    # Dateiendungen = wahrscheinlich Script-/FS-Aufgabe
    if re.search(r"\.(py|ps1|txt|csv|json|pdf|xlsx?|docx?|mp3|mp4)\b", lower):
        return True

    return False


# ---------------------------------------------------------------------------
# Plan-Datei schreiben
# ---------------------------------------------------------------------------

def _step_description(step: Dict[str, Any]) -> str:
    """Erzeugt eine lesbare Beschreibung eines Plan-Schritts."""
    kind = str(step.get("kind", "?"))
    descriptions = {
        "script_create": "Script erstellen",
        "script_exec":   "Script ausführen",
        "write_file":    "Datei schreiben",
        "read_file":     "Datei lesen",
        "delete_file":   "Datei löschen",
        "gmail_send_email": "E-Mail senden",
        "gmail_send_email_advanced": "E-Mail senden",
        "cron_create":   "Zeitplan anlegen",
        "list_directory": "Verzeichnis lesen",
        "script_validate": "Script validieren",
    }
    base = descriptions.get(kind, kind)
    # Dateiname oder Script-Pfad als Zusatz
    for field in ("script_path", "path", "name", "target"):
        val = str(step.get(field, "") or "")
        if val:
            name = Path(val).name if "/" in val or "\\" in val else val
            if name:
                return f"{base}: {name}"
    return base


def write_temp_plan(
    message: str,
    steps: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Optional[Path]:
    """
    Schreibt einen temporären Plan als JSON-Datei.
    Gibt den Pfad zurück, oder None bei Fehler.
    """
    try:
        _TEMP_PLAN_DIR.mkdir(parents=True, exist_ok=True)
        plan_id = uuid.uuid4().hex[:12]
        plan = {
            "id": plan_id,
            "goal": message[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "steps": [
                {
                    "idx": i,
                    "kind": str(s.get("kind", "?")),
                    "description": _step_description(s),
                    "status": "pending",
                }
                for i, s in enumerate(steps)
            ],
            "status": "running",
        }
        path = _TEMP_PLAN_DIR / f"{plan_id}.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Plan-Zusammenfassung für Telegram/WebUI
# ---------------------------------------------------------------------------

def format_plan_summary(message: str, steps: List[Dict[str, Any]]) -> str:
    """Erzeugt eine kompakte Telegram-freundliche Zusammenfassung des Plans."""
    goal_short = message.strip()[:120]
    if len(message.strip()) > 120:
        goal_short += "..."

    lines = [f"📋 *Plan* ({len(steps)} Schritte)", f"🎯 {goal_short}", ""]
    for i, step in enumerate(steps[:6], 1):
        desc = _step_description(step)
        lines.append(f"  {i}. {desc}")
    if len(steps) > 6:
        lines.append(f"  ... (+{len(steps) - 6} weitere)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plan-Schritt aktualisieren
# ---------------------------------------------------------------------------

def update_plan_step(
    plan_path: Optional[Path],
    step_idx: int,
    status: str,  # "running" | "done" | "failed" | "skipped"
) -> None:
    """Aktualisiert den Status eines einzelnen Schritts in der Plan-Datei."""
    if plan_path is None or not plan_path.exists():
        return
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for step in plan.get("steps", []):
            if step.get("idx") == step_idx:
                step["status"] = status
                break
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Plan abschließen
# ---------------------------------------------------------------------------

def finish_temp_plan(plan_path: Optional[Path], success: bool = True) -> None:
    """
    Schließt den Plan ab: setzt status=done/failed und verschiebt ihn ins
    Archiv-Verzeichnis (data/plans/archive/). Kein stilles Löschen – bleibt
    nachvollziehbar.
    """
    if plan_path is None or not plan_path.exists():
        return
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["status"] = "done" if success else "failed"
        plan["finished_at"] = datetime.now(timezone.utc).isoformat()
        # Alle noch "pending"/"running" Steps als skipped markieren
        for step in plan.get("steps", []):
            if step.get("status") in ("pending", "running"):
                step["status"] = "skipped" if not success else "done"

        archive_dir = ROOT_DIR / "data" / "plans" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / plan_path.name
        archive_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        plan_path.unlink(missing_ok=True)
    except Exception:
        pass


class TaskPlanner:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.plan_path: Optional[Path] = None

    def should_plan(self, message: str) -> bool:
        return should_plan(message)

    def create_hierarchical_plan(self, goal: str, steps: List[Dict[str, Any]]) -> Path:
        p = write_temp_plan(goal, steps, self.cfg)
        if p:
            self.plan_path = p
            return p
        raise RuntimeError("Failed to create plan file.")

    def update_step(self, step_idx: int, status: str, artifact: Optional[str] = None):
        update_plan_step(self.plan_path, step_idx, status)
        if artifact and self.plan_path and self.plan_path.exists():
             try:
                plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
                for s in plan.get("steps", []):
                    if s["idx"] == step_idx:
                        if "artifacts" not in s: s["artifacts"] = []
                        s["artifacts"].append(artifact)
                        break
                self.plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
             except Exception: pass

    def get_summary(self) -> str:
        if not self.plan_path or not self.plan_path.exists():
            return "Kein aktiver Plan."
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        done = sum(1 for s in plan["steps"] if s["status"] == "done")
        total = len(plan["steps"])
        return f"Plan-Fortschritt: {done}/{total} Schritte abgeschlossen ({plan['status']})."

def get_planner(cfg: Dict[str, Any]) -> TaskPlanner:
    return TaskPlanner(cfg)
