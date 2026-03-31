# K.AI Agent Doku

Stand: 2026-03-21 (Update: Gmail-Erweiterung, ReAct-Loop-Optimierung)

---

## Changelog

### 2026-03-21: Gmail-Erweiterung & ReAct-Loop-Optimierung
**Ziel:** Vollständige E-Mail-Body-Abfrage via neuem Tool, effizientere Iterations-Verwaltung im ReAct-Loop.

- **Neues Tool `gmail_get_message`:**
  - Ruft den vollständigen Inhalt einer einzelnen E-Mail per ID ab (`GET /messages/{id}?format=full`).
  - HTML-Body wird automatisch gestripped (Tags, Scripts, Styles entfernt, Entities dekodiert) → sauberer Plaintext, max. 15.000 Zeichen.
  - Löst das Problem dass `gmail_list_messages` nur Snippets (3000 Zeichen rohes HTML) lieferte und Tracking-Nummern o.ä. nicht extrahierbar waren.
- **`gmail_list_messages` erweitert:**
  - Neuer optionaler Parameter `include_body` (bool): lädt vollständigen Body aller gelisteten Mails auf einmal.
  - Beschreibung im Tool-Katalog präzisiert (Hinweis auf `gmail_get_message` für Einzelabruf).
- **ReAct-Loop: `mem_update_plan` zählt nicht mehr gegen Iterations-Limit:**
  - `mem_update_plan`, `mem_save_fact`, `mem_get_facts` sind nun "kostenlose" Operationen — sie erhöhen den Iterations-Zähler nicht.
  - Nur echte externe Tool-Calls (`gmail_*`, `sys_python_exec`, `web_fetch`, etc.) zählen gegen das konfigurierte Limit.
  - Hintergrund: Häufige Plan-Updates sind gewollt (externes Arbeitsgedächtnis des LLMs), dürfen aber nicht das Budget für echte Arbeit aufbrauchen.
  - Sicherheit: Bestehender `_consecutive_local_only >= 5`-Guard bleibt aktiv (warnt nach 5 Plan-Updates ohne echte Action).
- **Exception-Guard separater Counter:**
  - Neuer `_critical_errors`-Zähler für aufeinanderfolgende System-Exceptions im ReAct-Loop.
  - Vorher: `iteration`-Variable wurde missbraucht → brach fälschlicherweise nach N echten Tool-Calls + 1 Exception ab.
  - Jetzt: `_critical_errors > 5` bricht nur bei echtem Crash-Loop ab, unabhängig von der Tool-Call-Anzahl.

### 2026-03-18: System-Restore & Deep Integration Fixes
**Ziel:** Vollständige Wiederherstellung nach kritischem Import-Fehler, Optimierung der Tool-Ausführung und Stabilisierung der Messenger-Integration.

- **Import-Fix & Messenger-Recovery:**
  - Kritischer Fehler in `app/main.py` behoben (Import von `_workflow_stage_ctx` scheiterte aufgrund defekter `MessengerRuntime`-Mock-Klasse).
  - Echte `MessengerRuntime` aus Backup wiederhergestellt (Worker-Threads für Telegram/Discord wieder aktiv).
  - Signatur-Korrektur der Healthcheck-Funktionen (`telegram_healthcheck`, `discord_healthcheck`) zur Vermeidung von 500-Fehlern.
- **Execution Plane Security & Robustness:**
  - PowerShell-Executor auf **Base64-Encoding (`-EncodedCommand`)** umgestellt. Dies verhindert Syntax-Fehler bei komplexen Skripten mit Sonderzeichen (Pipes, Quotes, Backslashes).
  - Konsolidierung der Shell-Handler in `app/main.py` (nur noch ein universaler, robuster Weg für alle Shell-/Python-Befehle).
- **Self-Improvement & Patching:**
  - Patch-System erfolgreich live verifiziert (Backup -> Apply -> Syntax-Check -> Status).
  - **Gemini-Tool-Fix:** Autonomer Patch zur Bereinigung von JSON-Schemas für Google Gemini-Modelle angewendet (behebt `property is not defined` Fehler bei verschachtelten Tool-Definitionen).
- **Logging-Optimierung:**
  - Automatisches Cleaning von Backslashes im `audit.log`. Windows-Pfade werden vor der JSON-Serialisierung in das universelle `/`-Format konvertiert (verhindert `\\\\`-Maskierung).
- **Autonomie-Verifizierung:**
  - Erfolgreicher Live-Test: Agent hat autonom eine komplexe Playlist-Aufgabe (383 Beatles-Songs vom NAS `\\Medianas`) inklusive Code-Generierung und Ausführung gelöst.

### 2026-02-26: Cleanup – Web/Share/Map-Tools entfernt
**Ziel:** Tool-Stack vereinfachen, MCP/Dynamic-First, Alt-Tooling entfernen.

- Entfernt: `web_search`, `web_fetch`, `image_search`, `browser_*` Tools
- Entfernt: `share_file` / `send_file` Flow
- Entfernt: `map_network_drive` / `unmap_network_drive`
- Entfernt: `/api/config/web` und `/api/tests/brave`
- Setup/WebUI: Web-Konfiguration komplett entfernt und `config.json` bereinigt
- MCP/Dynamic/Scripts bleiben primary; verbleibende Built-ins als Fallback
- WebUI: neuer Simulator-Reiter fuer Intent/Tool-Plan-Simulation
- Memory: Offline-Fallback fuer Embeddings, falls SentenceTransformer-Model nicht geladen werden kann
- Setup: Option fuer SentenceTransformer-Model-Cache (Memory-Suche) mit Hinweistext
- Bereinigung: veraltete Doku-Dateien entfernt (WEB_CAPABILITIES, PROJECT_STATUS, REACT_LOOP_STATUS)
- Bereinigung: weitere Doku-Dateien entfernt (AUDIO_SETUP, PROMPT_CACHING, DEVELOPMENT_RULES, README). AGENTS bleibt erhalten.

**Hinweis:** Ältere Web-Tool-Doku ist ab diesem Stand deprecated.

---

## Architektur & Fehlerhandling (OpenClaw-Style Refactor)

### Intent-Flow
- intent_simple.py: Nur Intent-Parsing, keine Tool-Logik
- main.py: Dispatcher nimmt Intent-Objekte entgegen, orchestriert Tool-Calls
- Mehrstufig: LLM-Intent → Heuristik → Tool-Mapping

### Dispatcher/Tool-Execution (Execution Plane)
- Tool-Calls werden über eine isolierte **Execution Plane** (`app/execution_plane.py`) ausgeführt.
- Trennung von Logik (Main-Prozess) und Ausführung (Sub-Prozess).
- Sicherheit: Token-basierte Kommunikation, automatische Timeouts, Prozess-Isolation.
- Robustheit: PowerShell-Befehle werden Base64-kodiert übertragen, um Shell-Parsing-Probleme zu vermeiden.

### Feedback-Loop
- Nach Fehler/Timeout: Sofortige Rückmeldung an LLM, max. 3 Retries.
- Automatischer ReAct-Loop: Denken -> Handeln -> Beobachten -> Repeat.

### Logging/Monitoring
- Granulares Logging (`audit.log`, `errors.log`, `llm_calls.log`).
- Audit-Trail erfasst jede Stufe (Request, Interpretation, Policy, Execution, Response).

---

## Aktuelle Fähigkeiten (Living List)

### Konversation & Intelligenz
- **ReAct Multi-Step Planner**: Löst komplexe Aufgaben autonom durch sequentielle Planung und Ausführung.
- **Provider-Fallback**: Schaltet bei Ausfall eines LLM-Providers (z.B. Ollama) automatisch auf Alternativen (Gemini, Claude) um.
- **Hybrid Memory Search**: Kombination aus semantischer Vektorsuche (ChromaDB) und präzisem Keyword-Matching.

### Filesystem & Netzwerk
- Voller Zugriff auf lokales Filesystem und UNC-Netzwerkpfade (z.B. NAS).
- Unterstützung für alle Basis-Operationen (Listen, Lesen, Schreiben, Kopieren, Verschieben, Löschen).
- Robustes Handling von Pfaden mit Leerzeichen und Sonderzeichen.

### Skripte & Automatisierung
- Erstellung und Ausführung von Skripten in 18+ Sprachen (Python, PowerShell, JS/Node.js, etc.).
- **Node.js Dependency-Management**: Automatisches Nachinstallieren von npm-Paketen.
- **Cron-Scheduler**: Zeitbasierte Aufgaben mit Zustellung via Telegram, Discord oder WebUI.

### Messenger & Audio
- Nahtlose Integration von **Telegram** und **Discord**.
- Lokale Audio-Transkription via **Faster-Whisper**.
- Sprachausgabe (TTS) via **Edge-TTS** (10+ deutsche Stimmen).

### Skills (Externe Dienste)
- **Gmail** (`skills/gmail/`): E-Mails senden, listen und vollständig abrufen via Gmail API (OAuth2).
  - Tools: `gmail_send_email`, `gmail_send_email_advanced`, `gmail_list_messages`, `gmail_get_message`
- **Brave Search** (`skills/brave_search/`): Web-Suche via Brave Search API.
- **Thingiverse** (`skills/thingiverse/`): 3D-Modell-Suche via Thingiverse API.

### Selbstverbesserung (Self-Improvement)
- Autonome Diagnose von Fehlersignalen.
- Generierung und Anwendung von Code-Patches zur Systemoptimierung.
- Sicherheits-Backups und Syntax-Checks vor jeder Code-Änderung.

---

## 3) Konfiguration (`config.json`)

### Wichtige Felder (Auszug)
- `security.active_role`: `user` oder `admin`
- `security.execution_mode`: `deny`, `unrestricted`
- `execution_plane.enabled`: Trennung der Ausführungsebene (Best Practice).
- `self_improve.enabled`: Autonome Fehleranalyse aktiv.
- `mcp.servers`: Integration externer Tools via Model Context Protocol.

## 4) Sicherheitsmodell
- **Logisches Sandboxing**: Pfad-Validierung in `app/policy.py`.
- **Admin-Checks**: Bestimmte Aktionen erfordern echte Windows-Adminrechte.
- **Token-Schutz**: Kommunikation zur Execution Plane ist abgesichert.

---
*K.AI Agent - Hochleistungs-KI-Plattform für lokale Desktop-Automatisierung.*
