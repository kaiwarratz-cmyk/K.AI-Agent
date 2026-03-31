from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


def is_windows_admin() -> bool:
    if os.name != "nt":
        return os.getuid() == 0 if hasattr(os, "getuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def can_admin_actions(active_role: str) -> bool:
    return active_role == "admin" and is_windows_admin()


def _workspace_path(cfg: Dict[str, Any], root_dir: Path) -> Path:
    raw = str(cfg.get("workspace", "data\\workspace"))
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (root_dir / p).resolve()


def _is_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def validate_risky_paths(
    cfg: Dict[str, Any], root_dir: Path, paths: Iterable[str]
) -> Tuple[bool, str]:
    role = str(cfg.get("security", {}).get("active_role", "user")).lower()
    full_access = bool(cfg.get("filesystem", {}).get("full_access", False))
    workspace = _workspace_path(cfg, root_dir)
    checked = [Path(p).resolve() for p in paths if p]
    if not checked:
        return True, ""  # Keine Pfade zu prüfen -> Erlaubt.

    if role == "admin" and full_access:
        return True, ""

    outside = [str(p) for p in checked if not _is_within(workspace, p)]
    if outside:
        admin_proc = is_windows_admin()
        return (
            False,
            (
                f"Pfad ausserhalb Workspace nicht erlaubt. Workspace: {workspace}. "
                f"Betroffen: {', '.join(outside)}. "
                f"Aktuell: role={role}, full_access={full_access}, admin_process={admin_proc}. "
                "Fuer Outside-Zugriff: role=admin + full_access=true + Prozess als Windows-Admin."
            ),
        )
    return True, ""
