"""
sys_tools.py – Betriebssystem-Hilfsfunktionen für K.AI Agent.
"""
from __future__ import annotations
import os
import subprocess
from typing import Dict, Any


def sys_open_file(path: str) -> Dict[str, Any]:
    """Öffnet eine Datei oder URL mit der Standard-Anwendung des Betriebssystems.
    Nutzt os.startfile (Windows). Geeignet für PDFs, Bilder, Videos, Musik etc."""
    path = os.path.expandvars(path.strip())
    try:
        os.startfile(path)
        return {"ok": True, "reply": f"Geöffnet: {path}"}
    except Exception as e:
        return {"ok": False, "reply": f"Fehler beim Öffnen von '{path}': {e}"}
