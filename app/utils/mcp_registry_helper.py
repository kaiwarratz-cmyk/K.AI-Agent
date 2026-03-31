from __future__ import annotations
import json
import os
import pathlib
import re
import shutil
import zipfile
import threading
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import httpx
from app.tool_engine import tool_store
from app.config import save_config, ROOT_DIR

def _handle_mcp_registry_install(cfg: Dict[str, Any], source_id: str, name: str, mcp_register_fn: Any) -> Dict[str, Any]:
    """Lagert die komplexe Installations-Logik für MCP Registry aus."""
    from app.mcp_registry import install_from_registry
    
    source_id = str(source_id or "").strip()
    name = str(name or "").strip()
    if not source_id or not name:
        return {"ok": False, "message": "source_id/name fehlen."}
        
    try:
        res = install_from_registry(cfg, source_id, name)
        if not res.get("ok", False):
            return res
            
        proposal = res.get("proposal", {})
        
        # FALL A: Standard stdio/npx
        if proposal.get("type") == "stdio" and proposal.get("command"):
            action = {
                "name": name,
                "command": proposal.get("command"),
                "args": proposal.get("args", []),
                "env": proposal.get("env", {}),
                "type": "stdio",
            }
            _, msg = mcp_register_fn(cfg, action)
            save_config(cfg)
            return {"ok": True, "message": f"Tool '{name}' erfolgreich via Registry installiert."}
            
        # FALL B: GitHub Auto-Download & Configure
        if proposal.get("type") == "github_auto":
            detail_url = proposal.get("url", "")
            downloads_dir = (ROOT_DIR / "data" / "mcp_registry_downloads").resolve()
            downloads_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. Download ZIP
            zip_urls = []
            owner_repo = ""
            m = re.search(r"github.com/([^/]+/[^/]+)", detail_url)
            if m:
                owner_repo = m.group(1).rstrip("/")
                zip_urls.append(f"https://api.github.com/repos/{owner_repo}/zipball")
                zip_urls.append(f"https://github.com/{owner_repo}/archive/refs/heads/main.zip")
                zip_urls.append(f"https://github.com/{owner_repo}/archive/refs/heads/master.zip")
            
            saved_zip = None
            last_error = ""
            safe_name = re.sub(r"[^A-Za-z0-9]", "_", name)
            
            for url in zip_urls:
                try:
                    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                        r = client.get(url)
                        if r.status_code == 200 and len(r.content) > 500:
                            saved_zip = downloads_dir / f"{safe_name}.zip"
                            saved_zip.write_bytes(r.content)
                            break
                        else:
                            last_error = f"HTTP {r.status_code} für {url} ({len(r.content)} bytes)"
                except Exception as dl_exc:
                    last_error = f"{url}: {dl_exc}"
                    continue
                
            if not saved_zip:
                return {"ok": False, "message": f"Download von GitHub fehlgeschlagen: {last_error}"}
                
            # 2. Extract
            extract_to = downloads_dir / safe_name
            if extract_to.exists(): shutil.rmtree(extract_to, ignore_errors=True)
            
            # Temporary folder to extract and move
            temp_extract = downloads_dir / f"temp_{safe_name}"
            if temp_extract.exists(): shutil.rmtree(temp_extract, ignore_errors=True)
            temp_extract.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(saved_zip, 'r') as zip_ref:
                zip_ref.extractall(temp_extract)
                possible_folders = [d for d in os.listdir(temp_extract) if os.path.isdir(temp_extract / Path(d))]
                if possible_folders:
                    repo_name_part = owner_repo.split('/')[-1] if owner_repo else ""
                    match_folder = next((f for f in possible_folders if repo_name_part in f), possible_folders[0])
                    shutil.move(str(temp_extract / match_folder), str(extract_to))
            shutil.rmtree(temp_extract, ignore_errors=True)
            
            # 3. Guess Command & Install Deps
            import subprocess as _sp
            venv_path = ROOT_DIR / ".venv"
            python_exe = str((venv_path / "Scripts" / "python.exe").resolve()) if venv_path.exists() else "python"
            pip_exe = str((venv_path / "Scripts" / "pip.exe").resolve()) if venv_path.exists() else "pip"

            note = ""
            top_files_names = [f.name for f in extract_to.iterdir() if f.is_file()] if extract_to.exists() else []

            # Priorität: package.json → npm/node
            if "package.json" in top_files_names:
                try:
                    _sp.run(["npm", "install", "--no-audit", "--no-fund"], cwd=extract_to, shell=True, timeout=180)
                except Exception: pass
                
                action = {
                    "name": name,
                    "command": "npm",
                    "args": ["start"],
                    "cwd": str(extract_to),
                    "type": "stdio",
                }
                mcp_register_fn(cfg, action)
                save_config(cfg)
                return {"ok": True, "message": f"Node.js-Tool '{name}' installiert und via 'npm start' registriert."}

            # Python: setup.py oder requirements.txt
            if "requirements.txt" in top_files_names or "setup.py" in top_files_names or "pyproject.toml" in top_files_names:
                if "requirements.txt" in top_files_names:
                    try:
                        _sp.run([pip_exe, "install", "-r", "requirements.txt"], cwd=extract_to, shell=False, timeout=120)
                    except Exception: pass
                
                main_file = ""
                for candidate in ["main.py", "server.py", "app.py", f"{safe_name}.py"]:
                    if (extract_to / candidate).exists():
                        main_file = candidate
                        break
                
                if not main_file:
                    py_files = list(extract_to.glob("*.py"))
                    if py_files: main_file = py_files[0].name
                
                if main_file:
                    action = {
                        "name": name,
                        "command": python_exe,
                        "args": [str(extract_to / main_file)],
                        "cwd": str(extract_to),
                        "type": "stdio",
                    }
                    mcp_register_fn(cfg, action)
                    save_config(cfg)
                    return {"ok": True, "message": f"Python-Tool '{name}' installiert und via '{main_file}' registriert."}

            return {"ok": False, "message": f"Tool '{name}' wurde heruntergeladen, aber der Startbefehl konnte nicht automatisch ermittelt werden."}

        return {"ok": False, "message": f"Unbekannter Installationstyp für '{name}': {proposal.get('type')}"}
        
    except Exception as e:
        tool_store.log("mcp_registry_install_error", str(e))
        return {"ok": False, "message": f"Installation von '{name}' fehlgeschlagen: {e}"}
