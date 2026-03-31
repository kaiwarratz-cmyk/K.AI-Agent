"""
Zentrale Tool-Registry fuer K.AI Agent.
Konsolidiert alle Tool-Definitionen in einer hierarchischen Baumstruktur.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

# Hierarchische Tool-Visualisierung (Tree Format) für den System-Prompt
TOOL_CATALOG_TREE = {
    "📂 FILESYSTEM (fs)": [
        "fs_read_file(path): Liest den vollstaendigen Inhalt einer Datei (lokal oder UNC-Pfad).",
        "fs_write_file(path, content): Schreibt oder ueberschreibt eine Datei vollstaendig.",
        "fs_apply_patch(path, patch_text): Wendet einen Unified Diff (patch) auf eine Datei an. PFLICHT fuer komplexe Code-Aenderungen an mehreren Stellen einer Datei. Besser als fs_edit_replace da tolerant gegenueber kleinen Whitespace-Unterschieden.",
        "fs_append(path, content): Haengt Text an eine bestehende Datei an (kein Ueberschreiben). Fuer schrittweisen Aufbau: fs_write_file fuer Block 1, fs_append fuer alle weiteren.",
        "fs_edit_replace(path, old_str, new_string): Ersetzt exakt einen Textblock (old_str muss zeichengenau uebereinstimmen).",
        "fs_code_outline(path): Erstellt eine strukturelle Uebersicht (Klassen/Funktionen) einer Code-Datei. PFLICHT fuer Navigation in grossen Projekten.",
        "fs_search_symbol(name, path): Sucht nach einer Symboldefinition (Klasse/Funktion) im Workspace.",
        "fs_find_usages(symbol, path): Findet alle Stellen im Projekt, an denen ein Symbol verwendet wird. PFLICHT fuer Refactoring-Checks.",
        "fs_index_workspace(path): Indiziert den Workspace semantisch (Vektor-DB). PFLICHT fuer grosse Projekte.",
        "fs_search_codebase(query, top_k): Sucht semantisch in der indizierten Codebase (Fragen wie 'Wo wird das Error-Logging initialisiert?' moeglich).",
        "fs_find_files(path, pattern, recursive): Sucht Dateien nach DATEINAME/Muster. Unterstuetzt UNC-Pfade (\\\\server\\share), Wildcards (*.mp3) und mehrere Muster mit Semikolon (*.mp3;*.flac). Meldet explizit nicht zugaengliche Verzeichnisse (z.B. auf NAS). NICHT fuer Dateiinhalt-Suche – dafuer fs_grep verwenden.",
        "fs_grep(path, pattern, recursive): Sucht nach TEXT INNERHALB von Text-Dateien (zeilenweise Regex). NUR fuer Textdateien – NICHT fuer Binaerdateien (MP3, FLAC, Video, Bilder)! Fuer Dateinamen-Suche fs_find_files verwenden.",
        "fs_list_dir(path): Listet Inhalt eines Verzeichnisses auf (Dateien + Unterordner).",
        "fs_get_tree(path, max_depth): Zeigt Verzeichnisstruktur als Baum (Standard max_depth=3).",
        "fs_copy(src, dst): Kopiert eine Datei oder einen Ordner.",
        "fs_move(src, dst): Verschiebt oder benennt eine Datei/Ordner um.",
        "fs_rename(src, dst): Benennt eine Datei/Ordner um (Alias fuer fs_move).",
        "fs_delete(path, use_trash): Loescht eine Datei/Ordner (Standard: in Papierkorb, use_trash=false fuer permanent).",
        "fs_mkdir(path): Erstellt ein Verzeichnis (inkl. alle Elternordner).",
        "fs_zip_create(src_path, archive_path, recursive): Erstellt ein ZIP-Archiv aus einer Datei oder einem Ordner.",
        "fs_zip_extract(archive_path, target_dir): Entpackt ein ZIP-Archiv in ein Verzeichnis.",
    ],
    "🌐 NETWORK (net)": [
        "net_ping(host): Prueft ob ein Host/IP erreichbar ist.",
        "net_list_shares(host): Listet alle SMB-Freigaben eines Hosts auf (gibt UNC-Pfade zurueck).",
        "net_connect_share(host, share, drive_letter, username, password): Verbindet eine SMB-Freigabe via 'net use'. drive_letter/username/password optional.",
        "net_dns_lookup(host): Loest Hostnamen zu IP auf (und umgekehrt).",
        "net_http_status(url): Prueft HTTP-Erreichbarkeit einer URL (Statuscode + Antwortzeit).",
    ],
    "🌍 WEB (web)": [
        "web_search(query): Sucht im Internet nach Informationen, Dokumentationen oder aktuellen Ereignissen.",
        "web_fetch(url): Laedt den Textinhalt einer Webseite als sauberen Text. Automatischer JS-Fallback. Ergebnis direkt verwenden – NICHT als .html speichern oder mit BeautifulSoup parsen!",
        "web_fetch_smart(url, delay, max_chars, scroll): BEVORZUGT fuer JS-gerenderte Seiten. Gibt sauberes Markdown zurueck (KEIN rohes HTML). Extrahiert auch alle Links. Ergebnis direkt verwenden – kein Parsen noetig!",
        "web_fetch_js(url, selector, wait_selector, wait_ms): Alternative zu web_fetch_smart fuer JS-Seiten via Playwright. Gibt sauberen Text zurueck (KEIN HTML). Ergebnis direkt verwenden.",
        "web_fetch_json(url, params, headers): Ruft eine REST-JSON-API ab und liefert das geparste Objekt.",
        "web_post(url, data, as_json, headers): HTTP POST-Request (Formulardaten oder JSON). as_json=true fuer JSON-Body.",
        "web_download(url, dest_path): Laedt eine Datei aus dem Internet herunter. dest_path optional.",
    ],
    "🧠 MEMORY (mem)": [
        "mem_update_plan(content): MUST USE FOR COMPLEX TASKS. Schreibt Schritte/Todo-Liste in plan.md – nach jedem Schritt aktualisieren! Verhindert Orientierungsverlust bei langen Aufgaben.",
        "mem_save_fact(key, fact): Speichert wichtige Fakten DAUERHAFT – jobübergreifend abrufbar. PFLICHT am Ende jedes erfolgreichen Jobs für: (1) Tool-Pfade (arduino_cli_path, esptool_path), (2) Hardware-Infos (esp32_port=COM6, printer_ip=192.168.1.x), (3) erledigte Aufgaben (last_esp32_project=blink_3leds@2024-01-01), (4) Nutzer-Präferenzen (preferred_ide=vscode), (5) Projektpfade und Konfigurationen, (6) installierte pip-Pakete (pkg_cookidoo_api_installed=true), (7) Credentials-Alias (svc_cookidoo_credentials=stored_in_secrets:cookidoo_login). So kann der Agent bei Folgejobs direkt auf Vorwissen aufbauen statt von Null zu beginnen.",
        "mem_get_facts(): Liest alle bisher gespeicherten Fakten der Session.",
        "mem_delete_fact(key): Löscht einen veralteten Fakt aus dem Langzeitgedächtnis. PFLICHT wenn ein Fakt nicht mehr stimmt (anderer COM-Port, neue IP, geänderter Pfad).",
        "mem_get_secret(alias): Liest Zugangsdaten aus der sicheren Secrets-DB. PFLICHT wenn Credentials (API-Keys, Passwörter, Tokens) für einen Service benötigt werden — NIEMALS Zugangsdaten hartcodieren.",
        "mem_save_secret(alias, value): Speichert Zugangsdaten SICHER in der Secrets-DB. PFLICHT wenn der Nutzer Credentials eingibt — sofort speichern statt hardcoden. Danach mem_save_fact(key='svc_NAME_credentials', fact='stored_in_secrets:ALIAS') aufrufen."
    ],
    "💻 SYSTEM (sys)": [
        "sys_shell_command(command): Fuehrt PowerShell-Befehle aus. Timeout wird automatisch aus der Systemkonfiguration gesetzt.",
        "sys_cmd_exec(command, background?, timeout?): Fuehrt klassische CMD.EXE-Befehle aus. background=true fuer GUI-Apps/Spiele/Dienste (kehrt sofort zurueck statt zu haengen).",
        "sys_python_exec(code): HIGHLY RECOMMENDED! Fuehrt Python-Code aus. Ideal fuer: Dateiverarbeitung, JSON/CSV, REST APIs, os.walk auf grossen Verzeichnissen. PFLICHT: (1) open() IMMER mit encoding='utf-8'. (2) Windows-Pfade IMMER als raw-string r'C:\\pfad\\...' oder mit Forward-Slashes 'C:/pfad/...' – niemals mit einfachen Backslashes 'C:\\pfad\\tool\\...' da \\t,\\n,\\k als Escape-Sequenzen interpretiert werden und den Pfad korrumpieren!",
        "sys_screenshot(path, monitor): DPI-bewusster Screenshot (Win32 BitBlt). monitor=0=alle, 1=primaer.",
        "sys_open_file(path): Oeffnet eine Datei/URL mit der Standard-App des OS (PDF, Bild, Video, Musik etc.).",
        "terminal_background_run(command, cwd): Startet einen persistenten Hintergrundprozess (z.B. Server). Gibt eine process_id zurueck.",
        "terminal_read_output(process_id, timeout): Liest neuen Output eines Hintergrundprozesses. PFLICHT fuer Server-Monitoring.",
        "terminal_send_input(process_id, text): Sendet Standard-Input an einen laufenden Hintergrundprozess.",
        "terminal_terminate(process_id): Beendet einen Hintergrundprozess hart.",
        "send_messenger_file(path, caption): Sendet eine Datei direkt an den Nutzer via Telegram/Discord. MUSS aufgerufen werden wenn der Nutzer eine Datei angefordert hat! Nicht nur erwaehnen – tatsaechlich aufrufen!",
    ]
}

# Intents die keine Web-Tools brauchen (LLM kennt die Antwort aus Training)
_NO_WEB_INTENTS = {"script", "filesystem", "cron", "answer_and_save"}

def build_catalog_text(intent: Optional[str] = None) -> str:
    lines = ["### GLOBAL STRUCTURED TOOL CATALOG (Multi-Runtime V3) ###"]
    exclude_web = intent in _NO_WEB_INTENTS
    for category, tools in TOOL_CATALOG_TREE.items():
        if exclude_web and "WEB" in category:
            continue
        lines.append(f"\n{category}:")
        for t in tools:
            lines.append(f"  - {t}")
    return "\n".join(lines)

# Full OpenAI Function Definitions for Validation and LLM Dispatching
CORE_TOOLS: List[Dict[str, Any]] = [
    # --- FS TOOLS ---
    {"type": "function", "function": {"name": "fs_read_file", "description": "Liest den vollstaendigen Inhalt einer Datei (lokal oder UNC-Pfad).", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Absoluter Pfad oder UNC-Pfad (\\\\server\\share\\datei.txt)."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_write_file", "description": "Schreibt oder ueberschreibt eine Datei VOLLSTAENDIG. NUR verwenden fuer: (1) Neue Datei erstellen. (2) Kompletten Neuschrieb wenn >50% geaendert wird. NIEMALS fuer partielle Aenderungen an bestehenden Dateien – dafuer fs_edit_replace oder fs_append nutzen!", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Zieldateipfad."}, "content": {"type": "string", "description": "Vollstaendiger neuer Dateiinhalt."}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "fs_apply_patch", "description": "Wendet einen Unified Diff (patch) auf eine Datei an. PFLICHT fuer komplexe Code-Aenderungen an mehreren Stellen einer Datei. Besser als fs_edit_replace da tolerant gegenueber kleinen Whitespace-Unterschieden und Indentation-Fixes.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Zieldateipfad."}, "patch_text": {"type": "string", "description": "Der an stdin zu sendende Unified Diff (patch) Inhalt."}}, "required": ["path", "patch_text"]}}},
    {"type": "function", "function": {"name": "fs_edit_replace", "description": "Ersetzt exakt einen Textblock in einer bestehenden Datei – BEVORZUGTES TOOL fuer alle Code-Aenderungen. old_str muss zeichengenau uebereinstimmen (inkl. Einrueckung/Leerzeichen). Bei Fehler: fs_read_file ausfuehren und old_str nochmal exakt aus dem Dateiinhalt kopieren.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_str": {"type": "string", "description": "Exakt zu ersetzender Text (muss eindeutig in der Datei vorkommen)."}, "new_string": {"type": "string", "description": "Ersetzungstext."}}, "required": ["path", "old_str", "new_string"]}}},
    {"type": "function", "function": {"name": "fs_code_outline", "description": "Erstellt eine strukturelle Uebersicht (Klassen, Funktionen, Signaturen) einer Code-Datei. Ideal um Projekte effizient zu navigieren.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Pfad zur Datei."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_search_symbol", "description": "Sucht nach einer Symboldefinition (Klasse oder Funktion) im Workspace.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Name des Symbols (Klasse, Funktion)."}, "path": {"type": "string", "default": ".", "description": "Startpunkt fuer rekursive Suche."}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "fs_find_usages", "description": "Sucht alle Stellen (Referenzen) im Projekt, an denen ein Symbol verwendet wird. Ideal um Seiteneffekte bei Refactorings zu pruefen.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string", "description": "Name des zu suchenden Symbols."}, "path": {"type": "string", "default": ".", "description": "Startpunkt fuer die Suche."}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "fs_index_workspace", "description": "Indiziert den Workspace semantisch (Vektor-DB). Ermoeglicht spaeter effiziente semantische Suche.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": ".", "description": "Zupfad fuer rekursive Indizierung."}}, "required": []}}},
    {"type": "function", "function": {"name": "fs_search_codebase", "description": "Sucht semantisch in der indizierten Codebase nach Konzepten (z.B. 'Wo wird das Error-Logging initialisiert?').", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Suchbegriff oder Frage."}, "top_k": {"type": "integer", "default": 5, "description": "Maximale Anzahl an Treffern."}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "fs_find_files", "description": "Sucht Dateien nach DATEINAME/Muster (nicht Dateiinhalt!). Unterstuetzt UNC-Pfade (\\\\server\\share), Wildcards (*.mp3) und mehrere Muster mit Semikolon (*.mp3;*.flac). Meldet explizit nicht zugaengliche Verzeichnisse (z.B. auf NAS). Gibt alle Treffer zurueck. NICHT fuer Dateiinhalt-Suche – dafuer fs_grep verwenden.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Startverzeichnis (lokal oder UNC-Pfad, z.B. \\\\\\\\server\\\\share\\\\Musik)."}, "pattern": {"type": "string", "default": "*", "description": "Dateiname-Suchmuster, z.B. '*.mp3' oder '*.mp3;*.flac' oder 'Beatles'. Sucht NUR Dateinamen, nicht Inhalte!"}, "recursive": {"type": "boolean", "default": True, "description": "Unterordner einschliessen (Standard: true)."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_grep", "description": "Sucht nach TEXT INNERHALB von TEXT-Dateien (zeilenweise Regex, Dateiinhalt). NUR fuer Textdateien geeignet – NICHT fuer Binaerdateien (MP3, FLAC, Video, Bilder usw.)! Fuer Dateinamen-Suche fs_find_files verwenden.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Zu durchsuchendes Verzeichnis oder Datei (lokal oder UNC-Pfad)."}, "pattern": {"type": "string", "description": "Suchbegriff oder Regex fuer Dateiinhalte. Mehrere mit Semikolon trennen."}, "recursive": {"type": "boolean", "default": True}}, "required": ["path", "pattern"]}}},
    {"type": "function", "function": {"name": "fs_get_tree", "description": "Zeigt Verzeichnisstruktur als visuellen Baum.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "max_depth": {"type": "integer", "default": 3, "description": "Maximale Tiefe (Standard: 3)."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_list_dir", "description": "Listet Dateien und Unterordner eines Verzeichnisses auf.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Verzeichnispfad (lokal oder UNC)."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_copy", "description": "Kopiert eine Datei oder einen Ordner.", "parameters": {"type": "object", "properties": {"src": {"type": "string", "description": "Quellpfad."}, "dst": {"type": "string", "description": "Zielpfad."}}, "required": ["src", "dst"]}}},
    {"type": "function", "function": {"name": "fs_move", "description": "Verschiebt oder benennt eine Datei/Ordner um.", "parameters": {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}}},
    {"type": "function", "function": {"name": "fs_rename", "description": "Benennt eine Datei/Ordner um (Alias fuer fs_move).", "parameters": {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}}},
    {"type": "function", "function": {"name": "fs_delete", "description": "Loescht eine Datei oder einen Ordner. Standard: in Papierkorb (use_trash=true).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "use_trash": {"type": "boolean", "description": "True=Papierkorb (Standard), False=permanent loeschen."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_mkdir", "description": "Erstellt ein Verzeichnis (inkl. alle Elternordner).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "fs_append", "description": "Haengt Text an eine bestehende Datei an, ohne sie zu ueberschreiben. Verwenden wenn eine Datei schrittweise aufgebaut wird (erster Block per fs_write_file, alle weiteren per fs_append) oder fuer Log-Dateien/Listen die fortlaufend erweitert werden.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "fs_zip_create", "description": "Erstellt ein ZIP-Archiv aus einer Datei oder einem Ordner.", "parameters": {"type": "object", "properties": {"src_path": {"type": "string", "description": "Quelldatei oder -ordner."}, "archive_path": {"type": "string", "description": "Zielpfad fuer das ZIP-Archiv."}, "recursive": {"type": "boolean", "default": True}}, "required": ["src_path", "archive_path"]}}},
    {"type": "function", "function": {"name": "fs_zip_extract", "description": "Entpackt ein ZIP-Archiv in ein Zielverzeichnis.", "parameters": {"type": "object", "properties": {"archive_path": {"type": "string"}, "target_dir": {"type": "string"}}, "required": ["archive_path", "target_dir"]}}},
    # --- NET TOOLS ---
    {"type": "function", "function": {"name": "net_ping", "description": "Prueft ob ein Host oder eine IP erreichbar ist.", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Hostname oder IP-Adresse."}}, "required": ["host"]}}},
    {"type": "function", "function": {"name": "net_list_shares", "description": "Listet alle SMB-Netzwerkfreigaben eines Hosts auf (gibt UNC-Pfade zurueck).", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Hostname oder IP des Ziel-Servers."}}, "required": ["host"]}}},
    {"type": "function", "function": {"name": "net_dns_lookup", "description": "Loest einen Hostnamen zu einer IP-Adresse auf (oder umgekehrt).", "parameters": {"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]}}},
    {"type": "function", "function": {"name": "net_http_status", "description": "Prueft HTTP-Erreichbarkeit einer URL und gibt Statuscode sowie Antwortzeit zurueck.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "net_connect_share", "description": "Verbindet eine SMB-Netzwerkfreigabe via 'net use'. Optional als Netzlaufwerk.", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Hostname oder IP des Servers."}, "share": {"type": "string", "description": "Freigabename (z.B. 'Musik' fuer \\\\server\\Musik)."}, "drive_letter": {"type": "string", "description": "Optionaler Laufwerksbuchstabe (z.B. 'Z')."}, "username": {"type": "string", "description": "Optionaler Benutzername."}, "password": {"type": "string", "description": "Optionales Passwort."}}, "required": ["host", "share"]}}},
    # --- WEB TOOLS ---
    {"type": "function", "function": {"name": "web_search", "description": "Sucht im Internet nach Informationen, Dokumentationen oder aktuellen Ereignissen.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Suchanfrage."}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_fetch", "description": "Laedt den Textinhalt einer Webseite als sauberen Text. Automatischer JS-Fallback. Ergebnis direkt verwenden – NICHT als .html speichern oder mit BeautifulSoup parsen!", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "description": "Maximale Zeichen (Standard: 20000)."}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_fetch_smart", "description": "BEVORZUGT fuer JavaScript-gerenderte Seiten. Gibt sauberes Markdown zurueck (KEIN rohes HTML). Extrahiert auch alle Links. Ergebnis direkt verwenden – kein Parsen noetig!", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "delay": {"type": "number", "description": "Wartezeit nach Seitenladung in Sekunden (Standard: 3.0)."}, "max_chars": {"type": "integer", "description": "Maximale Markdown-Zeichen (Standard: 50000)."}, "scroll": {"type": "boolean", "description": "Seite scrollen um Lazy-Loading auszuloesen (Standard: true)."}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_fetch_js", "description": "Alternative zu web_fetch_smart fuer JS-Seiten via Playwright. Gibt sauberen Text zurueck (KEIN HTML). Ergebnis direkt verwenden.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}, "wait_selector": {"type": "string"}, "wait_ms": {"type": "integer"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_download", "description": "Laedt eine Datei aus dem Internet herunter.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "dest_path": {"type": "string", "description": "Optionaler Zielpfad (Standard: data/workspace/downloads/)."}, "max_mb": {"type": "integer", "description": "Maximale Dateigroesse in MB (Standard: 20480)."}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_fetch_json", "description": "Ruft eine REST-JSON-API per GET ab und liefert das geparste JSON-Objekt.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "params": {"type": "object", "description": "Optionale URL-Query-Parameter als Objekt."}, "headers": {"type": "object", "description": "Optionale HTTP-Header."}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "web_post", "description": "HTTP POST-Request. Sendet Formulardaten oder JSON an eine URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "object", "description": "Zu sendende Daten (Felder oder JSON-Objekt)."}, "as_json": {"type": "boolean", "description": "True=JSON-Body senden, False=Formulardaten (Standard: False)."}, "headers": {"type": "object", "description": "Optionale HTTP-Header."}}, "required": ["url", "data"]}}},
    # --- MEM TOOLS ---
    {"type": "function", "function": {"name": "mem_update_plan", "description": "Schreibt/aktualisiert den Aufgabenplan in plan.md. Bei komplexen Aufgaben nach jedem Schritt aufrufen.", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "Vollstaendiger Planinhalt (Markdown)."}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "mem_save_fact", "description": "Speichert einen Fakt DAUERHAFT im jobübergreifenden Langzeitgedächtnis – für alle zukünftigen Jobs sofort abrufbar. MUSS am Ende jedes erfolgreichen Jobs aufgerufen werden für: Tool-Pfade (arduino_cli_path, esptool_path), Hardware (esp32_port=COM6, printer_ip), abgeschlossene Projekte (last_esp32_project=blink_3leds), Nutzer-Präferenzen (preferred_language, preferred_ide), Systemkonfigurationen, API-Endpoints. Ziel: Agent baut bei Folgejobs direkt auf Vorwissen auf, statt alles neu zu suchen oder falsche Annahmen zu treffen.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Eindeutiger Schlüssel, z.B. 'arduino_cli_path', 'esp32_port', 'last_project_blink', 'user_pref_language'."}, "fact": {"type": "string", "description": "Zu speichernder Wert – vollständiger Pfad, Konfiguration, Ergebnis oder Präferenz."}}, "required": ["key", "fact"]}}},
    {"type": "function", "function": {"name": "mem_get_facts", "description": "Liest alle bisher gespeicherten Fakten der aktuellen Session.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "mem_delete_fact", "description": "Löscht einen veralteten Fakt aus dem jobübergreifenden Langzeitgedächtnis. MUSS aufgerufen werden wenn ein gespeicherter Fakt nicht mehr stimmt (z.B. COM-Port hat sich geändert, neue IP-Adresse, Tool wurde verschoben). Nach dem Löschen ggf. mem_save_fact mit dem korrekten Wert aufrufen.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Schlüssel des zu löschenden Fakts, z.B. 'esp32_port', 'arduino_cli_path'."}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "mem_get_secret", "description": "Liest Zugangsdaten (Passwort, API-Key, Token) aus der sicheren Secrets-DB. PFLICHT statt Credentials hardcoden — niemals Email/Passwort/Token direkt in Code schreiben!", "parameters": {"type": "object", "properties": {"alias": {"type": "string", "description": "Alias-Name des Eintrags, z.B. 'cookidoo_login', 'openai_key', 'telegram_token'."}}, "required": ["alias"]}}},
    {"type": "function", "function": {"name": "mem_save_secret", "description": "Speichert Zugangsdaten SICHER in der Secrets-DB. MUSS aufgerufen werden wenn der Nutzer Credentials eingibt (Passwort, API-Key, Token, Email+Passwort). Danach mem_save_fact(key='svc_NAME_credentials', fact='stored_in_secrets:ALIAS') aufrufen damit der Alias beim nächsten Job bekannt ist.", "parameters": {"type": "object", "properties": {"alias": {"type": "string", "description": "Eindeutiger Alias, z.B. 'cookidoo_login', 'openai_key'. Wird automatisch normalisiert (lowercase, nur a-z 0-9 _-)."}, "value": {"type": "string", "description": "Geheimwert: Passwort, API-Key, oder strukturiertes Format z.B. 'email=user@example.com|password=secret'."}}, "required": ["alias", "value"]}}},
    # --- SYS TOOLS ---
    {"type": "function", "function": {"name": "sys_shell_command", "description": "Fuehrt einen PowerShell-Befehl aus (empfohlen fuer Windows-Befehle). Timeout wird automatisch aus der Systemkonfiguration gesetzt.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "PowerShell-Befehl oder Skript."}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "sys_cmd_exec", "description": "Fuehrt einen klassischen CMD.EXE-Befehl aus. Timeout wird automatisch aus der Systemkonfiguration gesetzt. WICHTIG: Fuer GUI-Anwendungen (Fenster oeffnen), Spiele oder Dienste die dauerhaft laufen: background=true verwenden – startet den Prozess ohne zu warten und kehrt sofort zurueck. Ohne background=true wartet sys_cmd_exec auf Prozessende, was bei GUI-Apps zum Haengen fuehrt!", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "CMD-Befehl."}, "background": {"type": "boolean", "description": "true = Prozess detached starten, sofort zurueckkehren (fuer GUI-Apps, Spiele, Dienste). false/weglassen = warten bis Prozess beendet."}, "timeout": {"type": "integer", "description": "Timeout in Sekunden (wird automatisch auf Max-Wert aus Systemkonfiguration gecappt)."}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "sys_python_exec", "description": "Fuehrt Python-Code aus. Ideal fuer Dateiverarbeitung, JSON/CSV parsen, REST APIs, os.walk auf grossen Verzeichnissen und komplexe Textmanipulation. Timeout wird automatisch aus der Systemkonfiguration gesetzt. PFLICHT-REGELN: (1) open() IMMER mit encoding='utf-8'. (2) Windows-Pfade IMMER als raw-string r'C:\\pfad\\...' oder Forward-Slashes 'C:/pfad/...' – niemals einfache Backslashes, da \\t=Tab, \\n=Newline, \\k und andere den Pfad korrumpieren!", "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Python-Code. Pfade als r'C:\\pfad' oder 'C:/pfad' (niemals 'C:\\pfad' mit einfachen Backslashes!). open() immer mit encoding='utf-8'."}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "python_pip_install", "description": "Installiert Python-Pakete ins K.AI-venv (dasselbe Python das sys_python_exec verwendet). IMMER verwenden statt 'pip install' per Shell – Shell-pip trifft das falsche Python!", "parameters": {"type": "object", "properties": {"packages": {"type": "array", "items": {"type": "string"}, "description": "Liste der zu installierenden Pakete, z.B. [\"pyserial\", \"requests\"]."}}, "required": ["packages"]}}},
    {"type": "function", "function": {"name": "sys_screenshot", "description": "DPI-bewusster Screenshot (Win32 BitBlt, physische Pixel).", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Zielpfad fuer PNG-Datei (Standard: data/workspace/screenshots/screenshot_DATUM.png)."}, "monitor": {"type": "integer", "description": "0=alle Monitore (Standard), 1=nur primaerer Monitor."}}, "required": []}}},
    {"type": "function", "function": {"name": "sys_open_file", "description": "Oeffnet eine Datei oder URL mit der Standard-Anwendung des Betriebssystems.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Dateipfad oder URL."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "terminal_background_run", "description": "Startet einen persistenten Hintergrundprozess (z.B. Server). Gibt eine process_id zurueck, die für I/O verwendet werden kann.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Befehl zum Starten des Prozesses."}, "cwd": {"type": "string", "description": "Optionales Arbeitsverzeichnis (lokaler Pfad)."}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "terminal_read_output", "description": "Liest den aktuellen Output (stdout/stderr) eines Hintergrundprozesses. Leert die Queue der neuen Zeilen.", "parameters": {"type": "object", "properties": {"process_id": {"type": "string", "description": "Die ID aus terminal_background_run."}, "timeout": {"type": "number", "default": 0.5, "description": "Wartezeit in Sekunden falls Output leer ist."}}, "required": ["process_id"]}}},
    {"type": "function", "function": {"name": "terminal_send_input", "description": "Sendet Standard-Input an einen laufenden Hintergrundprozess.", "parameters": {"type": "object", "properties": {"process_id": {"type": "string"}, "text": {"type": "string", "description": "Der an stdin zu sendende Text."}}, "required": ["process_id", "text"]}}},
    {"type": "function", "function": {"name": "terminal_terminate", "description": "Beendet einen Hintergrundprozess hart.", "parameters": {"type": "object", "properties": {"process_id": {"type": "string"}}, "required": ["process_id"]}}},
    {"type": "function", "function": {"name": "send_messenger_file", "description": "Sendet eine Datei direkt an den Nutzer via Telegram oder Discord. MUSS aufgerufen werden wenn der Nutzer eine Datei angefordert hat (Playlist, Dokument, Bild usw.). Es reicht NICHT zu sagen 'Datei wurde gesendet' – der Tool-Call MUSS tatsaechlich erfolgen, sonst erhaelt der Nutzer nichts!", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Absoluter Pfad zur zu sendenden Datei. Forward-Slashes oder raw-string verwenden."}, "caption": {"type": "string", "description": "Optionaler Begleittext der Datei."}}, "required": ["path"]}}}
]

# Web-Tool-Namen für Intent-Filtering
WEB_TOOL_NAMES = {
    "web_search", "web_fetch", "web_fetch_smart", "web_fetch_js",
    "web_fetch_json", "web_post", "web_download", "brave_web_search",
}

# Legacy compatibility keys
ALLOWED_CORE_TOOL_NAMES = {
    "fs_read_file", "fs_write_file", "fs_edit_replace", "fs_find_files", "fs_grep", "fs_get_tree",
    "fs_list_dir", "fs_copy", "fs_move", "fs_rename", "fs_delete", "fs_mkdir", "fs_append", "fs_apply_patch",
    "fs_code_outline", "fs_search_symbol", "fs_find_usages", "fs_index_workspace", "fs_search_codebase",
    "fs_zip_create", "fs_zip_extract",
    "net_ping", "net_list_shares", "net_dns_lookup", "net_http_status", "net_connect_share",
    "web_search", "web_fetch", "web_download", "web_fetch_json", "web_post",
    "mem_update_plan", "mem_save_fact", "mem_get_facts", "mem_delete_fact", "mem_get_secret", "mem_save_secret",
    "sys_shell_command", "sys_cmd_exec", "sys_python_exec", "sys_screenshot", "sys_open_file",
    "terminal_background_run", "terminal_read_output", "terminal_send_input", "terminal_terminate",
    "send_messenger_file", "shell_command", "read_file", "write_file", "run_python", "run_cmd"
}

def get_tools_for_intent(intent: str) -> List[Dict[str, Any]]:
    return get_all_tools()

def get_all_tools() -> List[Dict[str, Any]]:
    return CORE_TOOLS + _mcp_tools() + _skill_tools()

def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    for tool in CORE_TOOLS:
        if tool.get("function", {}).get("name") == name: return tool
    for tool in _mcp_tools():
        if tool.get("function", {}).get("name") == name: return tool
    for tool in _skill_tools():
        if tool.get("function", {}).get("name") == name: return tool
    return None

def validate_tool_call(tool_name: str, args: Dict[str, Any]) -> tuple[bool, str]:
    tool = get_tool_by_name(tool_name)
    if not tool: return False, f"Unbekanntes Tool: {tool_name}"
    params_schema = tool.get("function", {}).get("parameters", {})
    required = params_schema.get("required", [])
    for req in required:
        if req not in args: return False, f"Fehlendes Pflichtfeld: {req}"
    return True, "OK"

def get_tool_names() -> List[str]:
    return [t.get("function", {}).get("name", "") for t in get_all_tools()]

def _mcp_tools() -> List[Dict[str, Any]]:
    try:
        from app.mcp_tools import get_cached_mcp_tools
        return [t for t in get_cached_mcp_tools() if isinstance(t, dict)]
    except Exception: return []

def _skill_tools() -> List[Dict[str, Any]]:
    try:
        from pathlib import Path
        from app.skills import load_skill_registry
        skills_dir = Path(__file__).parent.parent / "skills"
        state_path = Path(__file__).parent.parent / "data" / "skills_state.json"
        reg = load_skill_registry(skills_dir, state_path)
        tools = []
        action_schemas = reg.get("action_schemas", {}) if isinstance(reg.get("action_schemas", {}), dict) else {}
        for t in (reg.get("tools", []) if isinstance(reg.get("tools", []), list) else []):
            kind = str(t.get("kind", "") or "").strip()
            desc = str(t.get("description", "") or "").strip()
            if not kind:
                continue
            schema = action_schemas.get(kind, {})
            req_fields = schema.get("required", {}) if isinstance(schema.get("required", {}), dict) else {}
            opt_fields = schema.get("optional", {}) if isinstance(schema.get("optional", {}), dict) else {}
            properties: Dict[str, Any] = {}
            for f in req_fields:
                properties[f] = {"type": "string"}
            for f in opt_fields:
                properties[f] = {"type": "string"}
            tools.append({
                "type": "function",
                "function": {
                    "name": kind,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(req_fields.keys()),
                    },
                },
            })
        return tools
    except Exception:
        return []
