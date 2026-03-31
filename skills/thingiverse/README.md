# Thingiverse Skill

## Zweck
Sucht nach 3D-Druckmodellen auf Thingiverse und gibt Download-URLs fuer STL-Dateien zurueck.
Der Agent kann danach via `web_download` die STL-Datei herunterladen.

## Voraussetzung: API-Token (kostenlos)
1. Thingiverse-Account anlegen: https://www.thingiverse.com
2. App registrieren: https://www.thingiverse.com/developers/apps
3. **App Name**: beliebig (z. B. "K.AI Agent")
4. **App URL**: `http://localhost`
5. Nach dem Erstellen erscheint der **App Token** (Bearer Token)
6. Token in K.AI WebUI unter `Skills -> thingiverse -> Secret: thingiverse_api_token` eintragen

## Tools

### `thingiverse_search`
Sucht nach 3D-Modellen auf Thingiverse.
- **required**: `query` (Suchbegriff, z. B. "dragon", "Katze", "flexi snake")
- **optional**: `per_page` (Standard: 5, max: 30), `sort` (relevant/popular/newest)

### `thingiverse_get_files`
Gibt alle Dateien eines Modells zurueck (STL, OBJ, etc.) mit direkten Download-URLs.
- **required**: `thing_id` (Thingiverse Thing-ID, z. B. "4745107")
- Ergebnis enthaelt `download_url` fuer jede Datei

## Typischer Workflow des Agents
1. `thingiverse_search` mit Suchbegriff → liefert `id`, `name`, `public_url`
2. `thingiverse_get_files` mit der Thing-ID → liefert `download_url`
3. `web_download` mit der `download_url` → laedt STL-Datei in den Workspace

## Steuerung
- WebUI: Reiter `Skills` → Skill aktivieren, Secret setzen
- Messenger/Chat:
  - `/skill enable thingiverse`
  - `/skill secrets thingiverse`
  - `/skill disable thingiverse`

## Prompt-Beispiele
- `Suche auf Thingiverse nach einem Drachen und lade die STL-Datei herunter`
- `nutze thingiverse_search mit query=flexi dragon per_page=3`
- `nutze thingiverse_get_files mit thing_id=4745107`

## Hinweise
- Rate Limit: 300 Requests / 5 Minuten
- Der API-Token ist kostenlos und wird nicht bewertet/genehmigt fuer private Nutzung
- Download-URLs von Thingiverse erfordern den Bearer-Token im Header — der Agent nutzt
  `web_download` nur fuer oeffentliche Direktlinks. Falls der Download fehlschlaegt, ist
  der Link passwortgeschuetzt (selten). In diesem Fall: Link im Browser oeffnen.
