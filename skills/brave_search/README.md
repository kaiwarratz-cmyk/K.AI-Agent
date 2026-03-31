# Brave Search Skill

## Zweck
Websuche ueber die offizielle Brave Search API — stabiler und qualitativ hochwertiger als
das integrierte DuckDuckGo (scraping-basiert). Brave betreibt einen eigenen Suchindex.

## Voraussetzung: API Key (kostenlos)
1. https://brave.com/search/api/ aufrufen
2. "Get started for free" → Account anlegen
3. API Key kopieren (Free Tier: 2.000 Anfragen/Monat)
4. WebUI → `Skills` → `brave_search` → aktivieren + Key unter `brave_search_api_key` eintragen

## Tools

### `brave_web_search`
Allgemeine Websuche.
- **required**: `query`
- **optional**:
  - `count` (Treffer, Standard 5, max 20)
  - `country` (z. B. `de`, `us`)
  - `search_lang` (z. B. `de`, `en`)
  - `freshness` (z. B. `pd` = past day, `pw` = past week, `pm` = past month)

### `brave_news_search`
Aktuelle Nachrichten-Suche.
- **required**: `query`
- **optional**: wie `brave_web_search`

## Verhalten wenn aktiviert
Wenn Brave Search aktiviert ist und der Agent eine Websuche macht, bevorzugt er
`brave_web_search` automatisch gegenueber `web_search` (DuckDuckGo), da die
Tool-Beschreibung explizit "Bevorzuge dieses Tool" enthaelt.

## Steuerung
- WebUI: `Skills` → `brave_search` → aktivieren/deaktivieren
- Messenger:
  - `/skill enable brave_search`
  - `/skill disable brave_search`

## Prompt-Beispiele
- `Suche nach aktuellen Nachrichten ueber KI`
- `nutze brave_web_search mit query="3D Drucker Katzenhaus" count=5 search_lang=de`
- `nutze brave_news_search mit query="OpenAI" freshness=pw`

## Limits (Free Tier)
- 2.000 Anfragen/Monat
- 1 Anfrage/Sekunde
- Kein Bildersuchergebnis im Free Tier
