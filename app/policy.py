from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.security import can_admin_actions, validate_risky_paths


@dataclass
class PolicyDecision:
    ok: bool
    message: str = ""
    code: str = ""


def execution_mode(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("security", {}).get("execution_mode", "unrestricted")).lower()


def active_role(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("security", {}).get("active_role", "user")).lower()


def deny_if_mode_deny(cfg: Dict[str, Any]) -> Optional[PolicyDecision]:
    if execution_mode(cfg) == "deny":
        return PolicyDecision(ok=False, message="Ausfuehrung ist im Modus 'deny' deaktiviert.", code="mode_deny")
    return None


def collect_risky_paths(action: Dict[str, Any]) -> List[str]:
    risky_paths: List[str] = []
    # Häufige Keys, die Pfade enthalten können
    path_keys = {
        "path", "src", "dst", "folder", "src_dir", "dst_dir", "unc",
        "directory", "dir", "file", "archive_path", "target_dir", "script_path"
    }
    for k, v in action.items():
        if not isinstance(v, str):
            continue
        if k in path_keys or k.endswith("_path") or k.endswith("_dir"):
            risky_paths.append(v)
    return risky_paths


def validate_action_paths(cfg: Dict[str, Any], root_dir: Path, action: Dict[str, Any]) -> PolicyDecision:
    kind = str(action.get("kind", "")).strip().lower()
    # Actions without file paths need no path validation
    pathless_kinds = {
        "shell_command", "run_cmd", "run_python", "run_powershell",
        "web_fetch", "web_fetch_text", "web_fetch_js", "web_fetch_smart", "web_get_text", "web_search", "web_search_ddg",
        "web_public_data", "web_data", "web_links", "web_download",
        "cron_create", "cron_list", "cron_delete", "cron_pause", "cron_resume", "cron_test",
        "mcp_refresh_tools", "mcp_registry_search", "mcp_registry_prepare", "mcp_registry_install",
        "core_memory_update", "install_python_packages", "install_nodejs_packages",
        "gmail_send_email", "gmail_send_email_advanced", "gmail_list_messages",
        "thingiverse_search", "thingiverse_get_files",
        "brave_web_search", "brave_news_search",
    }
    if kind in pathless_kinds:
        return PolicyDecision(ok=True)
    risky_paths = collect_risky_paths(action)
    allowed, msg = validate_risky_paths(cfg, root_dir, risky_paths)
    if allowed:
        return PolicyDecision(ok=True)
    return PolicyDecision(ok=False, message=msg, code="path_denied")


def require_admin_for_risky(
    cfg: Dict[str, Any],
    *,
    is_risky: bool,
    admin_required: bool,
    role_hint: Callable[[Dict[str, Any]], str],
) -> Optional[PolicyDecision]:
    role = active_role(cfg)
    if is_risky and admin_required and not can_admin_actions(role):
        msg = "Diese Aktion ist nur im Admin-Modus mit echten Admin-Rechten erlaubt.\n" + role_hint(cfg)
        return PolicyDecision(ok=False, message=msg, code="admin_required")
    return None


def require_admin_for_any_risky(
    cfg: Dict[str, Any],
    *,
    is_risky: bool,
    role_hint: Callable[[Dict[str, Any]], str],
) -> Optional[PolicyDecision]:
    role = active_role(cfg)
    if is_risky and not can_admin_actions(role):
        msg = "Diese Aktion ist nur im Admin-Modus mit echten Admin-Rechten erlaubt.\n" + role_hint(cfg)
        return PolicyDecision(ok=False, message=msg, code="admin_required")
    return None


def require_admin_for_risky_scope(
    cfg: Dict[str, Any],
    *,
    is_risky: bool,
    action: Dict[str, Any],
    workspace: Path,
    is_within: Callable[[Path, Path], bool],
    role_hint: Callable[[Dict[str, Any]], str],
) -> Optional[PolicyDecision]:
    if not is_risky:
        return None
    role = active_role(cfg)
    if can_admin_actions(role):
        return None

    kind = str(action.get("kind", "")).strip().lower()
    # Executables/downloaded binaries stay admin-only even in workspace.
    hard_admin_kinds = {"run_downloaded_file"}
    if kind in hard_admin_kinds:
        msg = "Diese Aktion ist nur im Admin-Modus mit echten Admin-Rechten erlaubt.\n" + role_hint(cfg)
        return PolicyDecision(ok=False, message=msg, code="admin_required")

    risky_paths = collect_risky_paths(action)
    if not risky_paths:
        return None
    for raw in risky_paths:
        p = Path(str(raw)).resolve()
        if not is_within(workspace, p):
            msg = "Diese Aktion ist nur im Admin-Modus mit echten Admin-Rechten erlaubt.\n" + role_hint(cfg)
            return PolicyDecision(ok=False, message=msg, code="admin_required")
    # Workspace-scoped risky filesystem actions are allowed without Windows admin.
    return None


def check_script_exec_scope(
    cfg: Dict[str, Any],
    *,
    action: Dict[str, Any],
    workspace: Path,
    is_within: Callable[[Path, Path], bool],
    role_hint: Callable[[Dict[str, Any]], str],
) -> Optional[PolicyDecision]:
    if str(action.get("kind", "")) != "script_exec":
        return None
    role = active_role(cfg)
    if role == "admin":
        return None
    script_path_raw = str(action.get("script_path", "") or "").strip()
    script_owner = str(action.get("script_owner_role", "user")).lower()
    if script_owner == "admin":
        msg = (
            "Ausfuehrung verweigert: user darf keine vom admin erstellten Scripts ausfuehren.\n"
            + role_hint(cfg)
        )
        return PolicyDecision(ok=False, message=msg, code="script_owner_admin")
    if not script_path_raw:
        msg = (
            "Ausfuehrung verweigert: user darf nur Script-Dateien aus dem Workspace ausfuehren.\n"
            "Speichere das Script zuerst als Datei im Workspace.\n"
            + role_hint(cfg)
        )
        return PolicyDecision(ok=False, message=msg, code="script_no_path")
    script_path = Path(script_path_raw).resolve()
    if not is_within(workspace, script_path):
        msg = (
            f"Ausfuehrung verweigert: Script liegt ausserhalb des Workspace ({workspace}).\n"
            + role_hint(cfg)
        )
        return PolicyDecision(ok=False, message=msg, code="script_outside_workspace")
    return None
