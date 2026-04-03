# K.AI — Autonomer KI-Agent

> ⚠️ **Dieses Projekt befindet sich aktiv in Entwicklung.** Features, APIs und Konfigurationsformate können sich jederzeit ändern. Nicht für den Produktionseinsatz geeignet.

K.AI ist ein vollständig autonomer KI-Agent, der auf einem lokalen Windows-Host läuft und über Telegram, Discord oder eine WebUI gesteuert werden kann. Er kombiniert einen leistungsfähigen ReAct-Loop mit persistentem Langzeitgedächtnis, nativem Tool-Calling und einem erweiterbaren Skill-System — konzipiert als persönlicher Assistent mit echten Ausführungsrechten auf dem Host.

---

## Features

### Kernarchitektur
- **ReAct-Loop** — iterativer Reasoning & Acting Zyklus: Plant, führt aus, wertet aus, iteriert bis die Aufgabe wirklich abgeschlossen ist
- **Native Tool Calling** — LLM ruft Tools direkt auf, kein JSON-Parsing-Overhead
- **Multi-Provider LLM** — Gemini, GPT-4, Claude, Ollama (lokal), DeepSeek, Mistral, Groq u.v.m. — jederzeit wechselbar ohne Code-Änderung
- **Dialogue Engine** — intelligentes Routing: unterscheidet zwischen neuen Aufgaben, Gesprächen und Folgeanfragen
- **Persistent Session Memory** — Gesprächskontext wird sitzungsübergreifend gespeichert

### Gedächtnis & Wissen
- **ChromaDB Semantic Search** — Vektor-Embeddings für semantische Fact-Suche über alle gespeicherten Erkenntnisse
- **Auto-Learning** (`_auto_extract_facts_bg`) — nach jedem erfolgreichen Job extrahiert der Agent automatisch relevantes Wissen (API-Pfade, Konfigurationen, installierte Pakete) und speichert es für zukünftige Jobs
- **Secrets Store** — verschlüsselte Credential-Speicherung, niemals im Klartext im Code
- **Workspace-RAG** — Code-Index des lokalen Projekts für gezielte Codebase-Suche

### Sprache & Medien
- **STT (Speech-to-Text)** — Sprachnachrichten in Telegram/Discord werden automatisch via [faster-Whisper](https://github.com/SYSTRAN/faster-whisper) transkribiert und als Text-Aufgabe verarbeitet
- **TTS (Text-to-Speech)** — Antworten können als Sprachausgabe über [edge-tts](https://github.com/rany2/edge-tts) zurückgesendet werden
- **Vision / Bildanalyse** — Bilder die per Telegram/Discord gesendet werden, werden direkt vom LLM analysiert (sofern der gewählte Provider Vision unterstützt, z.B. Gemini, GPT-4o)
- **Datei-Handling** — der Agent empfängt Dateien jeglicher Art (PDF, CSV, ZIP, Bilder, Dokumente), verarbeitet sie und kann Dateien als Antwort zurückschicken (`send_messenger_file`)

### Messenger-Integration
- **Telegram** — vollständiger Bot-Support inkl. Datei-Upload/-Empfang, Sprach­nachrichten, Bilder, Inline-Status-Updates während der Ausführung
- **Discord** — Bot-Integration mit identischem Feature-Umfang
- **WebUI** — lokales Web-Interface auf Port 8765 mit Live-Output, Konfiguration und Job-Simulation

### Tool-Ökosystem

| Kategorie | Tools |
|-----------|-------|
| **Web** | `web_search`, `web_fetch_smart`, `web_fetch_js`, `web_fetch_json`, `web_post`, `web_download` |
| **Code-Ausführung** | `sys_python_exec` (persistente REPL-Session), `sys_cmd_exec`, `sys_shell_command` |
| **Terminal** | `terminal_background_run`, `terminal_read_output`, `terminal_send_input`, `terminal_terminate` |
| **Dateisystem** | `fs_read_file`, `fs_write_file`, `fs_edit_replace`, `fs_append`, `fs_apply_patch`, `fs_copy`, `fs_move`, `fs_delete`, `fs_mkdir`, `fs_get_tree`, `fs_find_files`, `fs_grep`, `fs_zip_create/extract` |
| **Codebase** | `fs_index_workspace`, `fs_search_codebase`, `fs_search_symbol`, `fs_code_outline`, `fs_find_usages` |
| **Netzwerk** | `net_ping`, `net_http_status`, `net_dns_lookup`, `net_connect_share`, `net_list_shares` |
| **Gedächtnis** | `mem_save_fact`, `mem_get_facts`, `mem_delete_fact`, `mem_save_secret`, `mem_get_secret`, `mem_update_plan` |
| **System** | `sys_screenshot`, `sys_open_file`, `python_pip_install`, `send_messenger_file` |
| **Gmail** | `gmail_list_messages`, `gmail_get_message`, `gmail_send_email_advanced` |
| **MCP** | Dynamische Integration beliebiger MCP-Server (Model Context Protocol) |

### Automatisierung
- **Cron-Jobs** — zeitgesteuerte Aufgaben direkt über natürliche Sprache erstellen: `"Erinnere mich jeden Montag um 9 Uhr an..."` → `cron_create`
- **Background Terminals** — lang laufende Prozesse im Hintergrund starten und überwachen
- **Browser Automation** — Playwright (headless Chromium) für Web-Scraping und UI-Automatisierung

### Skill-System
Erweiterbar durch YAML/JSON-definierte Skills im `/skills`-Ordner:
- **Gmail** — E-Mail lesen, schreiben, durchsuchen
- **Brave Search** — dedizierte Web-Suche über Brave Search API
- **Thingiverse** — 3D-Modell-Suche
- Eigene Skills einfach ergänzbar

### Sicherheit & Konfiguration
- **Execution Modes** — `unrestricted`, `supervised`, `deny` — granulare Kontrolle welche Tool-Calls automatisch ausgeführt werden
- **Policy Engine** — Sicherheitsregeln für gefährliche Operationen
- **Multi-Modell-Konfiguration** — pro Modell angepasste Tool-Profile (welche Tools für welches Modell erlaubt sind)

---

## Architektur

```
app/
├── main.py              → ReAct-Loop, Tool-Handler, Messenger-Integration
├── prompt_manager.py    → System-Prompt Builder (Persona + Verhaltensregeln)
├── context_manager.py   → discovered_facts DB + ChromaDB Semantic Search
├── chroma_memory.py     → ChromaDB Embeddings (all-MiniLM-L6-v2)
├── dialogue_engine.py   → Intent-Routing (new_task / simple / chat)
├── llm_router.py        → Multi-Provider LLM Abstraction
├── execution_plane.py   → Sandboxed Code Execution
├── tool_registry.py     → Tool-Katalog & Definitionen
├── messenger/           → Telegram & Discord Integration
│   ├── telegram.py
│   └── discord.py
└── tools/               → Tool-Implementierungen
    ├── python_exec.py   → Persistente REPL-Session
    ├── filesystem.py    → Dateisystem-Tools
    ├── web_toolkit.py   → Web-Tools
    └── ...

skills/                  → YAML/JSON-definierte Skills
persona.md               → Agent-Identität & Verhaltensregeln
config.example.json      → Konfigurationsvorlage (ohne echte Keys)
```

---

## Setup

### Voraussetzungen
- Python 3.10+
- Windows 10/11 (Linux möglich, nicht primär getestet)
- Optional: Ollama für lokale Modelle
- Optional: Telegram / Discord Bot Token

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/kaiwarratz-cmyk/K.AI-Agent.git
cd K.AI-Agent

# 2. Konfiguration anlegen
copy config.example.json config.json
# config.json mit Editor öffnen und API Keys eintragen

# 3. Installation starten
Install.bat
```

Oder manuell:
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Konfiguration (`config.json`)

```json
{
  "llm": {
    "active_provider_id": "gemini",
    "active_model": "gemini-2.5-flash"
  },
  "providers": {
    "gemini": { "api_key": "DEIN_GEMINI_API_KEY" },
    "ollama": { "base_url": "http://127.0.0.1:11434/v1" }
  },
  "messenger": {
    "telegram": { "bot_token": "DEIN_TELEGRAM_BOT_TOKEN" },
    "discord": { "bot_token": "DEIN_DISCORD_BOT_TOKEN" }
  }
}
```

### Starten

```bash
start_kai_agent.bat
# oder:
.venv\Scripts\python.exe -m app.main
```

WebUI dann unter: `http://localhost:8765`

---

## Provider-Support

| Provider | Modelle (Auswahl) | API Key |
|----------|-------------------|---------|
| **Gemini** | gemini-2.5-flash, gemini-2.5-pro | Google AI Studio |
| **Ollama** | llama3.1, qwen2.5-coder, deepseek-r1 | Nicht nötig (lokal) |
| **OpenAI** | gpt-4o, gpt-4.1, gpt-4.1-mini | OpenAI API |
| **Claude** | claude-3-5-sonnet, claude-3-7-sonnet | Anthropic |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | DeepSeek |
| **Groq** | llama-3.1-70b (schnell, kostenlos) | Groq Cloud |
| **Mistral** | mistral-large, mistral-small | Mistral AI |
| **Grok** | grok-2-latest | xAI |
| **Z.ai** | glm-4.7, glm-4.6, glm-4.5, glm-4.5-flash | Z.ai (Zhipu AI) |
| **OpenRouter** | 100+ Modelle über eine API | OpenRouter |

---

## Lizenz

MIT License — freie Nutzung, Modifikation und Weitergabe.
