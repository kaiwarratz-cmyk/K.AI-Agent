# K.AI Entwicklungsrichtlinien

Diese Datei wird bei JEDER Änderung am Projekt gelesen und eingehalten.
Keine Ausnahmen.

---

## Professionelle Umsetzung — kein Flickenteppich

**Vor jeder Implementierung:**
- Unsicher wie es richtig geht? → Erst recherchieren: Web-Suche nach Best Practices, Dokumentation lesen
- Orientierung an etablierten Systemen: ChatGPT Memory, Gemini, Claude Code — wie lösen die das?
- Lieber 10 Minuten recherchieren als 2 Stunden rückgängig machen

**Qualitätsmaßstab:**
- Würde das so in einem professionellen Produkt stehen?
- Ist die Lösung allgemein oder nur für diesen einen Fall?
- Würde ein Senior-Entwickler das so abnicken?

**Wenn nein → nicht implementieren, erst den richtigen Weg finden.**

---

## Grundprinzip: Keine Einzelfall-Lösungen

**VERBOTEN:**
- Spezifisches Bibliotheks-Wissen (z.B. Cookidoo, Selenium) in Systemregeln oder Code hardcoden
- Manuelle Einträge in `discovered_facts` DB als Ersatz für echtes Lernen
- Workarounds für einzelne Services/Libraries die nicht allgemein gelten

**RICHTIG:**
- Allgemeine Mechanismen bauen die für JEDEN Fall funktionieren
- Wenn ein Mechanismus für einen Fall versagt → den Mechanismus verbessern, nicht den Fall patchen

---

## Wo gehört was hin?

| Was | Wo | Begründung |
|-----|----|------------|
| Verhaltensregeln (immer headless, kein GUI) | `main.py` Systemregel | Reinstall-sicher, gilt allgemein |
| User-spezifische Daten (COM-Port, NAS-IP) | `discovered_facts` DB | Laufzeitdaten, user-spezifisch |
| Bibliotheks-Quirks (API-Signaturen etc.) | Nirgends hardcoden | Agent lernt selbst via `_auto_extract_facts_bg` |
| Credentials | `secrets.db` via `mem_save_secret` | Niemals im Code |

**Systemregeln in `main.py`** sind ALLGEMEINE Regeln:
- "Immer headless bei Browser-Automation" → gilt für Selenium, Playwright, alles
- "Nie Credentials in Code" → gilt immer
- "pip nur via python_pip_install" → gilt immer

**NICHT in Systemregeln:**
- "cookidoo-api importiert Cookidoo nicht CookidooAPI"
- "Selenium braucht --no-sandbox auf diesem System"
- Irgendwas das nur für einen konkreten Service/Job gilt

---

## Orientierung an etablierten KI-Assistenten

Bei jeder Feature-Entscheidung fragen: **Wie macht das ChatGPT / Gemini / Claude Code?**

| Feature | Referenz-Implementierung | Konsequenz für K.AI |
|---------|--------------------------|---------------------|
| Memory / Langzeitgedächtnis | ChatGPT Memory: automatisch extrahiert, semantisch abrufbar | `_auto_extract_facts_bg` + ChromaDB ✅ |
| Kontext-Injektion | ChatGPT: relevante Memories immer im Systemprompt | `retrieve_relevant_facts()` vor jedem Job ✅ |
| Credentials | Alle: niemals im Plaintext gespeichert | `secrets.db` + `mem_save_secret` ✅ |
| Browser-Automation | Professionelle Tools: Playwright (headless, kein ChromeDriver-Mismatch) | Systemregel ✅ |
| Fehler-Recovery | Alle: nach N gleichen Fehlern abbrechen, nicht endlos loopen | `_error_type_counts` + `_consecutive_tool_failures` ✅ |
| Code-Ausführung | Claude Code: persistente Session, kein State-Verlust zwischen Schritten | `PersistentSession` ✅ |

**Wenn ein Feature fehlt oder schlecht funktioniert:**
1. Schauen wie ChatGPT/Gemini/Claude Code es lösen
2. Best Practice recherchieren (Docs, GitHub, Papers)
3. Dann sauber implementieren — nicht raten

---

## Lern-Mechanismus (`_auto_extract_facts_bg`)

Der Agent lernt nach jedem erfolgreichen Job automatisch.
Wenn er eine Library falsch verwendet und es dann richtig macht → speichert er es selbst.

**Wenn der Lern-Mechanismus versagt:**
→ Den Mechanismus verbessern (Prompt, Kategorien, Logik)
→ NICHT manuell Facts eintragen

---

## Diagnose-Workflow bei Fehlern

1. Audit-Log lesen: `data/logs/audit.log`
2. Execution-Log lesen: `data/logs/execution_plane.log`
3. Wurzelursache identifizieren (nicht Symptom patchen)
4. Allgemeine Lösung implementieren
5. `py_compile` zum Verifizieren
6. Bot-Neustart kommunizieren

---

## Backups vor jeder Änderung

**PFLICHT vor jeder Änderung an einer bestehenden Datei:**
```bash
copy app\main.py app\main.py.bak
copy app\context_manager.py app\context_manager.py.bak
copy app\tool_registry.py app\tool_registry.py.bak
# usw. für jede betroffene Datei
```

- Backup-Datei benennen: `<datei>.bak` oder `<datei>.<datum>.bak`
- Bei größeren Änderungen: git commit vor der Änderung
- Backup NICHT löschen bis der Fix verifiziert und getestet ist

---

## Pflicht-Tests nach jeder Implementierung

### 1. Syntax-Check (IMMER, sofort nach jeder Änderung)
```bash
.venv/Scripts/python.exe -m py_compile app/main.py
.venv/Scripts/python.exe -m py_compile app/context_manager.py
.venv/Scripts/python.exe -m py_compile app/tool_registry.py
```
→ Kein "OK" = nichts committen, nichts dem User melden

### 2. Import-Check (bei neuen Funktionen/Klassen)
```bash
.venv/Scripts/python.exe -c "from app.context_manager import ContextManager; print('OK')"
.venv/Scripts/python.exe -c "from app.main import *; print('OK')"
```

### 3. Funktions-Test (bei Logik-Änderungen)
Jede neue Funktion direkt testen bevor sie als "fertig" gilt:
```bash
# Beispiel: retrieve_relevant_facts testen
.venv/Scripts/python.exe -c "
from app.context_manager import ContextManager
from pathlib import Path
ctx = ContextManager(Path('data/task_state.db'), Path('data/workspace'))
r = ctx.retrieve_relevant_facts('test query', top_k=3)
print('Ergebnis:', r)
"
```

### 4. Audit-Log-Verifikation (nach Bot-Neustart)
Nach dem ersten echten Job prüfen ob der Fix greift:
- Kein alter Fehler mehr im Log
- Neue Logik sichtbar (z.B. korrekte trace_id, korrekte Facts)

### 5. Was NICHT als "getestet" gilt
- "Sollte funktionieren" ohne Ausführung
- Nur Syntax-Check ohne Funktionstest
- Test in anderem Python als `.venv/Scripts/python.exe`

---

## Architektur-Übersicht

```
main.py              → ReAct-Loop, Systemregeln, Tool-Handler
tool_registry.py     → Tool-Katalog, CORE_TOOLS, ALLOWED_CORE_TOOL_NAMES
context_manager.py   → discovered_facts DB + ChromaDB Semantic Search
chroma_memory.py     → ChromaDB Embeddings (all-MiniLM-L6-v2)
tools/python_exec.py → PersistentSession REPL pro Job
```

**Datenfluss Fact-Learning:**
```
Job erfolgreich → _auto_extract_facts_bg() → LLM extrahiert api_*/cfg_*/pkg_* Facts
                                            → ctx_mgr.save_fact() → discovered_facts DB
                                            → ChromaDB sync
Nächster Job    → retrieve_relevant_facts(query) → ChromaDB Embedding-Suche
                                                  → Facts in Systemprompt injiziert
```

---

## Was bereits implementiert ist

- `mem_save_secret` / `mem_get_secret` (gibt JSON zurück)
- Semantische Fact-Suche via ChromaDB (ersetzt BM25)
- `_auto_extract_facts_bg` mit `api_*` / `cfg_*` / `api_*_limitations` Kategorien
- `PersistentSession` REPL pro Job (trace_id-basiert)
- **PROFESSIONAL Error Recovery** (wie ChatGPT/Gemini):
  - ModuleNotFoundError → konkrete `importlib.metadata` Diagnose-Kommandos
  - AttributeError → `dir()` + `help()` + `inspect.signature()`
  - TypeError → exakte Argument-Signatur anzeigen
  - SyntaxError → lokalen py_compile Hinweis
  - Nach jedem Fehler: konkrete nächste Schritte, kein "radikal ändern"
- Session-Reset nach 3 aufeinanderfolgende Fehlern (nicht blind abbrechen)
- Browser-Automation Regel: Playwright bevorzugen, immer headless
- trace_id Injection NUR für sys_python_exec (nicht fs_write_file, etc.)
