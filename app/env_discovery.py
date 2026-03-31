"""
Environment Discovery Module for K.AI Agent.
Scans the local system for available runtimes and tools.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import platform
from typing import Dict, Any, List


def discover_environment() -> Dict[str, Any]:
    """Scans the system for installed runtimes (Python, Node, GCC, etc)."""
    tools = {
        "runtimes": ["python", "node", "npm", "gcc", "go", "java"],
        "utilities": ["git", "curl", "ssh", "docker", "ffmpeg"],
        "compilers": ["g++", "rustc", "cargo"]
    }
    
    found_tools = {}
    for category, binaries in tools.items():
        versions = {}
        for bin_name in binaries:
            path = shutil.which(bin_name)
            if path:
                try:
                    # Versuche Version zu ermitteln
                    ver_cmd = [bin_name, "--version"]
                    if bin_name == "python": ver_cmd = ["python", "-V"]
                    if bin_name == "java": ver_cmd = ["java", "-version"]
                    
                    res = subprocess.run(ver_cmd, capture_output=True, text=True, timeout=2)
                    output = (res.stdout or res.stderr).strip()
                    ver_str = output.split('\n')[0].strip() if output else "unknown"
                    versions[bin_name] = {"path": path, "version": ver_str}
                except Exception:
                    versions[bin_name] = {"path": path, "version": "unknown"}
        
        if versions:
            found_tools[category] = versions

    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "available_runtimes": found_tools,
        "shell_type": os.environ.get("SHELL", "cmd.exe" if os.name == "nt" else "sh")
    }


def refresh_host_state() -> Dict[str, str]:
    """Live Host-State für jede ReAct-Iteration. Zeigt aktuellen Zustand des Systems."""
    from datetime import datetime
    try:
        import psutil
    except ImportError:
        # Graceful fallback wenn psutil nicht verfügbar
        return {
            "timestamp": datetime.now().isoformat(),
            "note": "psutil nicht installiert - Systemzustand nicht verfügbar"
        }

    result = {
        "timestamp": datetime.now().isoformat(),
        "cpu_usage_percent": f"{psutil.cpu_percent(interval=0.05)}%",
        "memory_usage_percent": f"{psutil.virtual_memory().percent}%",
        "disk_free_gb": f"{psutil.disk_usage('/').free / (1024**3):.1f}",
        "processes_count": str(len(psutil.pids())),
    }

    # Git branch falls vorhanden
    try:
        import pathlib
        _root = pathlib.Path(__file__).parent.parent.resolve()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(_root),
            timeout=1
        ).strip()
        result["git_branch"] = branch
    except Exception:
        result["git_branch"] = "keine"

    # Python venv status
    try:
        venv_path = os.environ.get("VIRTUAL_ENV", "keine")
        if venv_path and venv_path != "keine":
            result["python_venv"] = "aktiv"
        else:
            result["python_venv"] = "keine"
    except Exception:
        result["python_venv"] = "unbekannt"

    return result


def format_env_for_llm(env_data: Dict[str, Any]) -> str:
    """Formats the discovered environment data as a concise prompt injection."""
    import pathlib
    parts = [f"System: {env_data['os']} ({env_data['architecture']})"]
    parts.append(f"Shell: {env_data['shell_type']}")

    try:
        _root = (pathlib.Path(__file__).parent.parent).resolve()
        _ws   = (_root / "data" / "workspace").resolve()
        _cfg  = (_root / "data" / "config.json").resolve()
        _venv = (_root / ".venv" / "Scripts" / "python.exe").resolve()

        parts.append(f"K.AI Root:            {_root}")
        parts.append(f"Konfigurationsdatei:  {_cfg}  ← Tokens, API-Keys, Messenger-Einstellungen")
        parts.append(f"Workspace-Verzeichnis:{_ws}  ← Projektdateien, Tools, Downloads")
        parts.append(f"Venv Python:          {_venv}  ← IMMER dieses Python für sys_python_exec nutzen")
        parts.append(f"WICHTIG: .venv/ ist ein großes Paketverzeichnis — NIEMALS rekursiv durchsuchen.")
    except Exception:
        pass

    rt = env_data.get("available_runtimes", {})
    if rt:
        parts.append("Available Runtimes & Tools (im PATH):")
        for cat, items in rt.items():
            for name, info in items.items():
                parts.append(f"  - {name}: {info['version']} ({info['path']})")

    return "\n".join(parts)
