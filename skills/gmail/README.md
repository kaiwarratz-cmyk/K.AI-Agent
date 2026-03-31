# Gmail Skill

## Zweck
Sendet und listet E-Mails ueber die Gmail API.

## Dateien
- `skill.json`: Tool-/Handler-Definition
- `skill_config.json`: Default-Konfiguration (z. B. `token_secret`, `user_id`)

## Tools
- `gmail_send_email`
  - required: `to`, `subject`, `body`
  - optional: `thread_id`
- `gmail_send_email_advanced`
  - required: `to`, `subject`
  - optional: `body`, `html_body`, `attachments`, `cc`, `bcc`, `reply_to`, `thread_id`
- `gmail_list_messages`
  - required: `-`
  - optional: `query`, `max_results`, `include_body` (bool, liefert vollstaendigen Body je Mail)
  - Hinweis: Gibt Betreff, Absender, Datum, ID und Snippet zurueck. Fuer vollstaendigen Body einzelner Mails `gmail_get_message` nutzen.
- `gmail_get_message`
  - required: `message_id` (ID aus `gmail_list_messages`)
  - optional: `-`
  - Liefert vollstaendigen E-Mail-Body als bereinigten Plaintext (HTML wird automatisch gestripped, max. 15.000 Zeichen).

## Secrets
- required: `gmail_access_token`
- optional fuer Auto-Refresh:
  - `gmail_refresh_token`
  - `gmail_client_id`
  - `gmail_client_secret`

## Steuerung
- WebUI: Reiter `Skills` -> Skill aktivieren/deaktivieren, Secret setzen
- WebUI: Button `Gmail verbinden` startet den OAuth-Flow automatisch (Token-Speicherung im Callback)
- Messenger/Chat:
  - `/skills`
  - `/skill secrets gmail`
  - `/skill connect gmail`
  - `/skill enable gmail`
  - `/skill disable gmail`
  - `/skill reload`

## Prompt-Beispiele
- Direkt:
  - `nutze gmail_send_email mit to=... subject=... body=...`
  - `nutze gmail_send_email_advanced mit to=... subject=... body=... attachments=a.png,b.pdf`
- Cron:
  - `erstelle einen cronjob alle 10 minuten und nutze gmail_send_email mit to=... subject=... body=...`

## Token-Refresh
- Wenn `gmail_access_token` ungueltig/abgelaufen ist (HTTP 401), versucht der Skill automatisch zu erneuern.
- Dafuer muessen die optionalen Secrets oben gesetzt sein.
- Der neue Access Token wird danach wieder unter `gmail_access_token` gespeichert.

## OAuth Connect (automatisch)
- Voraussetzungen:
  - `gmail_client_id` und `gmail_client_secret` sind gesetzt.
  - OAuth-Client in Google ist als `Web application` angelegt.
  - Redirect URI in Google ist gesetzt auf:
    - `http://127.0.0.1:8000/api/skills/gmail/connect/callback`
- Kurzanleitung (bis zum Button-Klick):
  1. Google Cloud Console oeffnen: `https://console.cloud.google.com/`.
  2. Oben das richtige Projekt waehlen (Projekt-Dropdown neben dem Google-Cloud-Logo).
  3. Gmail API aktivieren:
     - `APIs & Services -> Library`
     - nach `Gmail API` suchen
     - `Enable` klicken
  4. OAuth-Consent-Screen vorbereiten:
     - `APIs & Services -> OAuth consent screen`
     - App-Typ `External` (oder passend fuer deine Umgebung)
     - App Name + Support-Mail setzen
     - speichern
     - falls Status `Testing`: unter `Test users` dein Gmail-Konto hinzufuegen
  5. OAuth Client anlegen:
     - `APIs & Services -> Credentials`
     - `+ CREATE CREDENTIALS -> OAuth client ID`
     - Application type: `Web application`
  6. Redirect URI eintragen bei `Authorized redirect URIs`:
     - `http://127.0.0.1:8000/api/skills/gmail/connect/callback`
     - optional zusaetzlich: `http://localhost:8000/api/skills/gmail/connect/callback`
  7. Speichern klicken. Danach zeigt Google den Dialog mit:
     - `Your Client ID`
     - `Your Client Secret`
  8. Falls Dialog schon geschlossen ist:
     - `APIs & Services -> Credentials`
     - unter `OAuth 2.0 Client IDs` den eben erstellten Web-Client anklicken
     - dort stehen `Client ID` und `Client secret` erneut
  9. In K.AI Agent unter `Skills -> gmail` die Secrets setzen:
     - `gmail_client_id`
     - `gmail_client_secret`
  10. Danach im WebUI auf `Gmail verbinden` klicken.
- Ablauf:
  - WebUI `Gmail verbinden` oder Messenger `/skill connect gmail`.
  - Nach Google-Freigabe speichert K.AI Agent Access/Refresh-Token automatisch in den Secrets.
