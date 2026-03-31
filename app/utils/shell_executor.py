from __future__ import annotations
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _decode_bytes(data: bytes) -> str:
    """Dekodiert Bytes robust mit verschiedenen Encodings."""
    if not data:
        return ""
    for enc in ["utf-8", "cp850", "latin-1"]:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

def _run_process(cmd: List[str], timeout: int = 120, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Führt einen Prozess aus und fängt Ausgaben robust ab."""
    from app.config import ROOT_DIR
    _cwd = cwd if cwd else str(ROOT_DIR)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            shell=False,
            cwd=_cwd,
            env=env,
            # Wir verzichten auf text=True um manuell zu dekodieren
        )
        return {
            "stdout": _decode_bytes(proc.stdout),
            "stderr": _decode_bytes(proc.stderr),
            "returncode": proc.returncode
        }
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": _decode_bytes(e.stdout or b""),
            "stderr": f"Timeout nach {timeout}s\n" + _decode_bytes(e.stderr or b""),
            "returncode": -1
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}

def _clean_powershell_clixml(text: str) -> str:
    """Entfernt PowerShell CLIXML-Formatierung aus STDERR."""
    if not text.startswith("#< CLIXML"):
        return text
    import re
    # XML Header und Tags entfernen, encodierte Newlines umwandeln
    cleaned = re.sub(r'#< CLIXML\r?\n', '', text)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    cleaned = cleaned.replace('_x000D__x000A_', '\n')
    cleaned = cleaned.replace('_x001B_', '\x1b')
    return cleaned.strip()

def _run_powershell(script: str, timeout: int = 120, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Führt ein PowerShell-Script aus."""
    # Wir nutzen Base64 Encoding für das Script, um Probleme mit Sonderzeichen/Escaping zu vermeiden
    import base64

    # Sicherstellen, dass Ausgaben als UTF-8 codiert werden und Fehler transparent sind
    setup_script = "$ErrorActionPreference = 'Continue'; $ProgressPreference = 'SilentlyContinue'; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    full_script = setup_script + script

    # UTF-16LE ist das von PowerShell für -EncodedCommand erwartete Format
    encoded_script = base64.b64encode(full_script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_script]
    res = _run_process(cmd, timeout=timeout, cwd=cwd, env=env)
    if "stderr" in res and res["stderr"]:
        res["stderr"] = _clean_powershell_clixml(res["stderr"])
    return res

def _run_python(code: str, timeout: int = 120, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Führt Python-Code aus."""
    from app.config import ROOT_DIR
    venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    py_exe = str(venv_py) if venv_py.exists() else sys.executable
    return _run_process([py_exe, "-c", code], timeout=timeout, cwd=cwd)

def _run_cmd(command: str, timeout: int = 60, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Führt einen CMD-Befehl aus."""
    return _run_process(["cmd", "/c", command], timeout=timeout, cwd=cwd)

def _run_shell_universal(command: str, timeout: int = 300, kind: str = "shell_command", cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    """
    Zentrales Shell-Tool. Nutzt PowerShell als Standard.
    Gibt stdout und stderr direkt an das Modell zurück.
    """
    if kind == "shell_python":
        res = _run_python(command, timeout=timeout, cwd=cwd)
    elif kind == "shell_cmd":
        res = _run_cmd(command, timeout=timeout, cwd=cwd)
    else:
        res = _run_powershell(command, timeout=timeout, cwd=cwd, env=env)
    
    out = (res.get("stdout") or "").strip()
    err = (res.get("stderr") or "").strip()
    rc = int(res.get("returncode", 0))
    
    result_parts = []
    if out:
        result_parts.append(f"stdout:\n{out}")
    if err:
        result_parts.append(f"stderr:\n{err}")
        
    if not result_parts:
        if rc == 0:
            result_text = (
                "Exit-Code: 0 — keine Textausgabe.\n"
                "Hinweis: Wenn ein Prozess gestartet werden sollte, ist unklar ob er läuft. "
                "sys_cmd_exec background=True liefert nach 1,5s einen Alive-Check."
            )
        else:
            result_text = f"Exit-Code: {rc} — Befehl fehlgeschlagen, keine Textausgabe."
    else:
        result_text = "\n\n".join(result_parts)
        if rc != 0:
            result_text = f"[Exit Code {rc}]\n{result_text}"

    return kind, result_text

def list_entries(path: str = ".", want: str = "all") -> str:
    """Listet Dateien und Verzeichnisse auf (Helfer für Modelle)."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Fehler: Pfad {path} existiert nicht."
        
        items = list(p.iterdir())
        if not items:
            return f"Pfad {path} ist leer."
            
        lines = [f"Inhalt von {p}:"]
        for item in items:
            if want == "files" and not item.is_file(): continue
            if want == "dirs" and not item.is_dir(): continue
            
            t = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"{t} {item.name}")
            
        return "\n".join(lines)
    except Exception as e:
        return f"Fehler beim Auflisten: {e}"
