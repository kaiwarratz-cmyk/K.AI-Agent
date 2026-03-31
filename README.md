# K.AI — Autonomer KI-Agent

K.AI ist ein autonomer KI-Agent der auf einem lokalen Host läuft und über Telegram (oder WebUI) gesteuert werden kann. Er verfügt über ein persistentes Gedächtnis, kann Code ausführen, das Web durchsuchen, Dateien verwalten und komplexe Aufgaben autonom lösen.

## Features

- **ReAct-Loop** — iterative Reasoning & Acting Architektur (wie GPT-4 Plugins / Claude Code)
- **Persistentes Gedächtnis** — ChromaDB Vektor-Embeddings + SQLite `discovered_facts`
- **Multi-Provider LLM** — Gemini, GPT-4, Claude, Ollama (lokal), DeepSeek u.v.m.
- **Tool-Ökosystem** — Web-Suche, Python-Ausführung, Dateisystem, Gmail, Playwright Browser-Automation, Cron-Jobs
- **Telegram-Integration** — vollständiger Messenger-Support inkl. Datei-Upload/-Download
- **Skill-System** — erweiterbar durch YAML-definierte Skills in `/skills`
- **Self-Improving** — der Agent lernt nach jedem Job automatisch aus seinen Erfahrungen

## Architektur

```
app/
├── main.py              # ReAct-Loop, Tool-Handler, Messenger-Integration
├── prompt_manager.py    # System-Prompt Builder (Persona + Regeln)
├── context_manager.py   # discovered_facts DB + ChromaDB Semantic Search
├── chroma_memory.py     # ChromaDB Embeddings (all-MiniLM-L6-v2)
├── dialogue_engine.py   # Intent-Routing (new_task / simple / chat)
├── llm_router.py        # Multi-Provider LLM Abstraction
├── execution_plane.py   # Sandboxed Code Execution
└── tool_registry.py     # Tool-Katalog & Definitionen

skills/                  # Erweiterbare YAML-Skills
persona.md               # Agent-Identität & Verhaltensregeln
config.example.json      # Konfigurationsvorlage (ohne echte Keys!)
```

## Setup

### Voraussetzungen
- Python 3.10+
- Windows 10/11 (getestet), Linux möglich
- Ollama (optional, für lokale Modelle)
- Telegram Bot Token (optional)

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/DEIN_USERNAME/K.AI.git
cd K.AI

# 2. Konfiguration anlegen
cp config.example.json config.json
# config.json bearbeiten: API Keys eintragen, Provider wählen

# 3. Installation starten
Install.bat
# oder manuell:
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Konfiguration (`config.json`)

Kopiere `config.example.json` nach `config.json` und trage deine Keys ein:

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
    "telegram": { "bot_token": "DEIN_TELEGRAM_BOT_TOKEN" }
  }
}
```

### Starten

```bash
start_kai_agent.bat
# oder:
.venv\Scripts\python.exe -m app.main
```

## Verwendung

### Telegram
Schreib deinem Bot einfach eine Aufgabe:
- `Recherchiere aktuelle Tech-News aus Deutschland`
- `Erstelle ein Python-Skript das die CPU-Auslastung loggt`
- `Suche auf eBay nach gebrauchten GPUs unter 200€`

### WebUI
Öffne `http://localhost:8765` nach dem Start.

## Provider-Support

| Provider | Modelle | Key nötig |
|----------|---------|-----------|
| Gemini | gemini-2.5-flash, gemini-2.5-pro | Google AI Studio |
| Ollama | llama3.1, qwen2.5-coder, deepseek | Nein (lokal) |
| OpenAI | gpt-4o, gpt-4.1 | OpenAI API |
| Claude | claude-3-5-sonnet | Anthropic |
| DeepSeek | deepseek-chat | DeepSeek |

## Lizenz

MIT License — freie Nutzung, Modifikation und Weitergabe.
