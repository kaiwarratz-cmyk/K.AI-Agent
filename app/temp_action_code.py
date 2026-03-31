def _execute_action_local(action: Dict[str, Any]) -> tuple[str, str]:
    # Parameter-Aliase für bessere Robustheit
    if "directory" in action and "path" not in action: action["path"] = action.pop("directory")
    if "file" in action and "path" not in action: action["path"] = action.pop("file")
    if "text" in action and "content" not in action: action["content"] = action.pop("content", action.pop("text", ""))
    if "body" in action and "content" not in action: action["content"] = action.pop("body")
    if "cmd" in action and "command" not in action: action["command"] = action.pop("cmd")
    
    # Kind auslesen
    kind = str(action.get("kind", "filesystem")).strip()
    
    # Falls das LLM nur 'param' nutzt, auf den einzigen Pflichtparameter mappen
    if "param" in action:
        spec = _action_schemas().get(kind, {})
        req_keys = list(spec.get("required", {}).keys())
        if len(req_keys) == 1 and req_keys[0] not in action:
            action[req_keys[0]] = action.pop("param")
    
    if kind == "dynamic_tool_create":
        return kind, "FEHLER: dynamic_tool_create ist deaktiviert. Nutze stattdessen 'sys_python_exec' für komplexe Logik." 
        
    # Backwards-compatibility: map legacy action kinds to current names
    try:
        alias_map = {
            "gmail_send": "gmail_send_email",
            "gmail_send_advanced": "gmail_send_email_advanced",
            "gmail_list": "gmail_list_messages",
        }
        if kind in alias_map:
            kind = alias_map[kind]
            action["kind"] = kind
    except Exception:
        pass

    ok, err = _validate_action_schema(action)
    if not ok:
        raise ValueError(f"Action-Schema ungueltig: {err}")
    if kind in ("shell_command", "shell_cmd", "shell_python"):
        command = str(action.get("command", action.get("script", action.get("code", action.get("cmd", "")))))
        timeout = int(action.get("timeout", 300))
        # Nutzt den korrigierten universal runner mit typspezifischer Ausfuehrung und Workspace-CWD
        import os
        from app.config import ROOT_DIR
        cwd = str((ROOT_DIR / "data" / "workspace").resolve())
        os.makedirs(cwd, exist_ok=True)
        _, result_text = _run_shell_universal(command, timeout=timeout, kind=kind, cwd=cwd)
        return kind, result_text
    
    if kind == "mcp_refresh_tools":
        from app.mcp_tools import refresh_mcp_tools
        return refresh_mcp_tools(_cfg())
    if kind == "mcp_register_server":
        return _mcp_register_server(_cfg(), action)
    if kind == "mcp_remove_server":
        return _mcp_remove_server(_cfg(), action)
    if kind == "mcp_registry_search":
        from app.mcp_registry import search_registry_sources
        query = str(action.get("query", "") or "").strip()
        limit = int(action.get("limit", 15) or 15)
        items = search_registry_sources(_cfg(), query, limit=limit)
        if not items:
            return "mcp_registry_search", "Keine Registry-Ergebnisse gefunden."
        lines = []
        for idx, it in enumerate(items[:limit], 1):
            name = str(it.get("name", "") or "").strip()
            src = str(it.get("source_name") or it.get("source_id") or "source")
            desc = str(it.get("description", "") or "").strip()
            hint = f"{name} ({src})"
            if desc:
                hint = f"{hint} - {desc}"
            lines.append(f"{idx}. {hint}")
        return "mcp_registry_search", "Gefundene MCP-Server:\n" + "\n".join(lines)
    if kind == "mcp_registry_prepare":
        from app.mcp_registry import get_registry_details, suggest_server_from_details
        source_id = str(action.get("source_id", "") or "").strip()
        name = str(action.get("name", "") or "").strip()
        if not source_id or not name:
            return "mcp_registry_prepare", "source_id/name fehlen."
        details = get_registry_details(_cfg(), source_id, name)
        if not details.get("ok", False):
            return "mcp_registry_prepare", str(details.get("message", "Registry-Details fehlen."))
        proposal = suggest_server_from_details(details)
        if not proposal.get("ok", False):
            return "mcp_registry_prepare", str(proposal.get("message", "Kein Vorschlag verfuegbar."))
        server = proposal.get("server", {})
        cmd = server.get("command")
        args = server.get("args", [])
        return "mcp_registry_prepare", f"Vorschlag: command={cmd} args={args}."
    if kind == "mcp_registry_install":
        from app.mcp_registry import install_from_registry
        source_id = str(action.get("source_id", "") or "").strip()
        name = str(action.get("name", "") or "").strip()
        if not source_id or not name:
            return "mcp_registry_install", "source_id/name fehlen."
        res = install_from_registry(_cfg(), source_id, name)
        if not res.get("ok", False):
            return "mcp_registry_install", str(res.get("message", "Install-Vorschlag fehlgeschlagen."))
        server = res.get("proposal", {})
        action = {
            "name": name,
            "command": server.get("command"),
            "args": server.get("args", []),
            "env": server.get("env", {}),
            "type": server.get("type", "stdio"),
        }
        return _mcp_register_server(_cfg(), action)
    if kind == "core_memory_update":
        from app.memory_system import MemoryManager
        mem_mgr = MemoryManager(_cfg())
        category = str(action.get("category", "fact")).strip().lower()
        key = str(action.get("key", "")).strip()
        value = action.get("value")
        # Langen Text abfangen: für mehrzeilige/lange Werte besser write_file verwenden
        if isinstance(value, str) and len(value) > 500:
            return "core_memory_update", (
                f"Fehler: value zu lang ({len(value)} Zeichen). "
                "core_memory_update ist nur für kurze Fakten (max ~200 Zeichen). "
                "Für längere Texte: write_file benutzen."
            )
        mem_mgr.update_core_memory(category, key, value)
        tool_store.log("core_memory", f"Fakt gespeichert: {category}/{key}")
        return "core_memory_update", f"Ich habe mir gemerkt: {category} -> {key}: {value}"
    if kind == "script_validate":
        return _execute_script_validate_action(action)
    if kind == "script_create":
        return _execute_script_create_action(action)
    if kind == "script_exec":
        return _execute_script_action(action)
    if kind == "install_python_packages":
        return _execute_install_python_packages_action(action)
    if kind == "install_nodejs_packages":
        return _execute_install_nodejs_packages_action(action)
    if kind == "run_downloaded_file":
        return _execute_downloaded_file_action(action)
    # ── WEB TOOLKIT (Core – kein LLM-Script nötig) ──────────────────────────
    if kind in {"web_fetch", "web_fetch_text", "web_get_text"}:
        from app.tools.web_toolkit import fetch_text
        import warnings as _w; _w.filterwarnings("ignore")
        url = str(action.get("url", "") or "").strip()
        if not url:
            return "web_fetch", "Fehler: 'url' Parameter fehlt."
        res = fetch_text(url,
                         timeout=int(action.get("timeout", 15) or 15),
                         max_chars=int(action.get("max_chars", 20000) or 20000),
                         selector=str(action.get("selector", "") or ""))
        if res.get("ok"):
            t = res.get("text", "")
            note_trunc = " [gekürzt]" if res.get("truncated") else ""
            return "web_fetch", f"[{res.get('title','')!s}] ({url}){note_trunc}\n\n{t}"
        return "web_fetch", f"Fehler beim Abruf von {url}: {res.get('error','?')}"
    if kind == "web_fetch_js":
        from app.tools.web_toolkit import fetch_text_js
        import warnings as _w; _w.filterwarnings("ignore")
        url = str(action.get("url", "") or "").strip()
        if not url:
            return "web_fetch_js", "Fehler: 'url' Parameter fehlt."
        res = fetch_text_js(
            url,
            timeout=int(action.get("timeout", 30) or 30),
            max_chars=int(action.get("max_chars", 20000) or 20000),
            selector=str(action.get("selector", "") or ""),
            wait_selector=str(action.get("wait_selector", "") or ""),
            wait_ms=int(action.get("wait_ms", 2000) or 2000),
        )
        if res.get("ok"):
            t = res.get("text", "")
            note_trunc = " [gekürzt]" if res.get("truncated") else ""
            return "web_fetch_js", f"[{res.get('title','')!s}] ({url}){note_trunc}\n\n{t}"
        return "web_fetch_js", f"Fehler beim JS-Abruf von {url}: {res.get('error','?')}"
    if kind == "web_fetch_smart":
        from app.tools.web_toolkit import fetch_smart
        import warnings as _w; _w.filterwarnings("ignore")
        url = str(action.get("url", "") or "").strip()
        if not url:
            return "web_fetch_smart", "Fehler: 'url' Parameter fehlt."
        res = fetch_smart(
            url,
            delay=float(action.get("delay", 3.0) or 3.0),
            max_chars=int(action.get("max_chars", 50000) or 50000),
            scroll=bool(action.get("scroll", True)),
            js_code=str(action.get("js_code", "") or ""),
            filter_links=str(action.get("filter_links", "") or ""),
        )
        if res.get("ok"):
            md = res.get("markdown", "")
            note_trunc = " [gekürzt]" if res.get("truncated") else ""
            links = res.get("links", [])
            links_section = ""
            if links:
                links_section = f"\n\n--- LINKS ({res.get('links_count', 0)} gesamt) ---\n" + "\n".join(links[:100])
            return "web_fetch_smart", f"[{res.get('title','')!s}] ({url}){note_trunc}\n\n{md}{links_section}"
        return "web_fetch_smart", f"Fehler bei web_fetch_smart für {url}: {res.get('error','?')}"
    if kind == "web_links":
        from app.tools.web_toolkit import extract_links
        import warnings as _w; _w.filterwarnings("ignore")
        url = str(action.get("url", "") or "").strip()
        if not url:
            return "web_links", "Fehler: 'url' Parameter fehlt."
        res = extract_links(url,
                            filter_pattern=str(action.get("filter_pattern", "") or ""),
                            same_domain=bool(action.get("same_domain", False)))
        if res.get("ok"):
            links = res.get("links", [])
            lines = [f"{i}. {l['text'] or '(kein Text)'} → {l['href']}" for i, l in enumerate(links, 1)]
            return "web_links", f"{res['count']} Links gefunden:\n" + "\n".join(lines[:200])
        return "web_links", f"Fehler: {res.get('error','?')}"
    if kind in {"web_download", "web_download_file"}:
        from app.tools.web_toolkit import download_file
        import warnings as _w; _w.filterwarnings("ignore")
        url = str(action.get("url", "") or "").strip()
        if not url:
            return "web_download", "Fehler: 'url' Parameter fehlt."
        _dl_cfg = _cfg()
        _dl_dk = str(_dialog_key_ctx.get("") or "").strip()
        _dl_filename = url.split("/")[-1].split("?")[0] or "Datei"

        def _dl_progress(pct: int, mb_done: float, mb_total: float) -> None:
            if pct == 100:
                msg = f"✅ {_dl_filename} — {mb_done:.1f} MB heruntergeladen"
            elif pct < 0 or mb_total <= 0:
                # Unbekannte Gesamtgröße
                msg = f"⬇️ {_dl_filename}\n{mb_done:.1f} MB heruntergeladen..."
            else:
                bar_filled = int(pct / 5)
                bar = "█" * bar_filled + "░" * (20 - bar_filled)
                msg = f"⬇️ {_dl_filename}\n[{bar}] {pct}% — {mb_done:.1f} / {mb_total:.1f} MB"
            _react_push_status(msg, _dl_cfg, _dl_dk)

        res = download_file(url,
                            dest_path=str(action.get("dest_path", "") or ""),
                            max_mb=int(action.get("max_mb", 20480) or 20480),
                            progress_cb=_dl_progress if _dl_dk else None)
        if res.get("ok"):
            return "web_download", f"Download OK: {res['path']} ({res['mb']} MB)"
        return "web_download", f"Download Fehler: {res.get('error','?')}"
    if kind in {"web_search", "web_search_ddg"}:
        from app.tools.web_toolkit import search_web
        query = str(action.get("query", "") or "").strip()
        if not query:
            return "web_search", "Fehler: 'query' Parameter fehlt."
        res = search_web(query,
                         max_results=int(action.get("max_results", 10) or 10))
        if res.get("ok"):
            results = res.get("results", [])
            lines = [f"{i}. {r.get('title','?')}\n   {r.get('href','')}\n   {r.get('body','')[:200]}"
                     for i, r in enumerate(results, 1)]
            return "web_search", f"{res['count']} Treffer:\n\n" + "\n\n".join(lines)
        if res.get("rate_limited"):
            return "web_search", res["error"]
        return "web_search", f"Suche fehlgeschlagen: {res.get('error','?')}"
    if kind in {"web_public_data", "web_data"}:
        from app.tools.web_toolkit import fetch_public_data
        import warnings as _w; _w.filterwarnings("ignore")
        data_kind = str(action.get("data_kind", "") or action.get("type", "weather")).strip()
        location = str(action.get("location", "") or action.get("city", "")).strip()
        res = fetch_public_data(data_kind, location=location, **{
            k: v for k, v in action.items()
            if k not in {"kind", "data_kind", "type", "location", "city"}
        })
        if res.get("ok"):
            if "text" in res:
                return "web_public_data", res["text"]
            if "data" in res:
                return "web_public_data", json.dumps(res["data"], ensure_ascii=False, indent=2)
            return "web_public_data", json.dumps({k: v for k, v in res.items() if k != "ok"},
                                                  ensure_ascii=False)
        return "web_public_data", f"Fehler: {res.get('error','?')}"
    # ── END WEB TOOLKIT ──────────────────────────────────────────────────────
    # MCP tools (mcp_* or cached MCP names)
    if str(kind).startswith("mcp_") or _is_cached_mcp_tool(kind):
        return _execute_mcp_tool(_cfg(), kind, action)

    # ── NEW STRUCTURED TOOLS (FS, NET, GIT, MEM, SYS) ────────────────────────
    if kind.startswith(("fs_", "net_", "git_", "mem_", "sys_")):
        try:
            import os
            from app.config import ROOT_DIR
            cwd = str((ROOT_DIR / "data" / "workspace").resolve())
            os.makedirs(cwd, exist_ok=True)

            # Alle fs_* Tools nutzen die Python-Implementierung (nicht PowerShell)
            # PowerShell hatte Probleme mit Pfaden mit Sonderzeichen wie (1974)
            if kind.startswith("fs_"):
                # VALIDIERUNG: fs_find_files darf NIEMALS mit erfundenen Pfaden aufgerufen werden
                if kind == "fs_find_files":
                    import os
                    path = str(action.get("path", ".")).strip()
                    norm_path = os.path.normpath(path)
                    # Prüfe ob Basis-Pfad existiert
                    if not os.path.exists(norm_path):
                        return kind, (
                            f"❌ STOPP: Pfad existiert NICHT: {path}\n"
                            f"Das ist HALLUZINATION! Du darfst KEINE Verzeichnisnamen erfinden!\n"
                            f"\n"
                            f"KORREKT: Nutze fs_list_dir ZUERST um den echten Pfad zu sehen,\n"
                            f"DANN fs_find_files mit BEWÄHRTEM Pfad aufrufen.\n"
                            f"\n"
                            f"Fehlerhaft: fs_find_files('{path}', '*dubstep*')\n"
                            f"Richtig: 1) fs_list_dir('\\\\\\\\Medianas\\\\Musik - Emulatoren - Backup')\n"
                            f"        2) fs_list_dir('\\\\\\\\Medianas\\\\Musik - Emulatoren - Backup\\\\Musik')\n"
                            f"        3) DANN fs_find_files mit ECHTEM Pfad\n"
                        )
                from app.tools import filesystem as fs_mod
                if hasattr(fs_mod, kind):
                    func = getattr(fs_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind.startswith("net_"):
                from app.tools import network as net_mod
                if hasattr(net_mod, kind):
                    func = getattr(net_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind.startswith("git_"):
                from app.tools import git as git_mod
                if hasattr(git_mod, kind):
                    func = getattr(git_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind.startswith("mem_"):
                from app.tools import memory as mem_mod
                if hasattr(mem_mod, kind):
                    func = getattr(mem_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind == "sys_shell_command":
                action["kind"] = "shell_command"
                return _execute_action_local(action)
            elif kind == "sys_cmd_exec":
                from app.tools import cmd as cmd_mod
                res = cmd_mod.run_cmd(**{k: v for k, v in action.items() if k != "kind"})
                return kind, f"CMD_STDOUT: {res.get('stdout')}\nCMD_STDERR: {res.get('stderr')}\nEXIT_CODE: {res.get('returncode')}"
            elif kind == "sys_python_exec":
                from app.tools import python_exec as py_mod
                res = py_mod.run_python(**{k: v for k, v in action.items() if k != "kind"})
                return kind, f"PYTHON_STDOUT: {res.get('stdout')}\nPYTHON_STDERR: {res.get('stderr')}\nEXIT_CODE: {res.get('returncode')}"
            elif kind.startswith("web_"):
                from app.tools import web_toolkit as web_mod
                if hasattr(web_mod, kind):
                    func = getattr(web_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind == "fs_grep":
                from app.tools import filesystem as fs_mod
                return kind, str(fs_mod.fs_grep(**{k: v for k, v in action.items() if k != "kind"}))
            elif kind.startswith("net_"):
                from app.tools import network as net_mod
                if hasattr(net_mod, kind):
                    func = getattr(net_mod, kind)
                    return kind, str(func(**{k: v for k, v in action.items() if k != "kind"}))
        except Exception as e:
            return kind, f"ERROR executing structured tool {kind}: {e}"

    try:
        return execute_filesystem_action(action)
    except Exception:
        raise


