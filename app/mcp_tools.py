from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.tool_engine import tool_store


from app.trace_utils import run_coro_sync

ROOT_DIR = Path(__file__).resolve().parent.parent
MCP_CACHE_PATH = ROOT_DIR / "data" / "mcp_tools_cache.json"
MCP_DB_PATH = ROOT_DIR / "data" / "mcp_tools.db"
LOCAL_SERVER_NAME = "local_dynamic"


def _run_coro_sync(coro, timeout: Optional[int] = None):
    return run_coro_sync(coro, timeout=float(timeout) if timeout else None)


def refresh_mcp_tools(cfg: Dict[str, Any]) -> Tuple[str, str]:
    ok, msg = mcp_available()
    if not ok:
        tool_store.log("mcp_refresh_error", msg)
        return "mcp_refresh_tools", f"MCP-Refresh fehlgeschlagen: {msg}"
    ensure_local_server(cfg)
    _cleanup_dynamic_registry_and_cache()
    from app.mcp_client import get_mcp_manager
    mgr = get_mcp_manager(cfg)  # cfg übergeben damit Server-Liste aktuell ist
    timeout = int(cfg.get("mcp", {}).get("timeout", 45))
    timeout = max(5, min(1800, timeout))
    try:
        tools = _run_coro_sync(mgr.get_all_tools(), timeout=timeout + 15)
        import time
        data = {"tools": tools, "refreshed_at": int(time.time())}
        MCP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Accept all tools (no external validator)
        valid_tools = tools
        invalid_tools = []

        data_to_write = {"tools": valid_tools, "refreshed_at": data.get("refreshed_at")}
        MCP_CACHE_PATH.write_text(json.dumps(data_to_write, ensure_ascii=False, indent=2), encoding="utf-8")

        # persist into json cache only
        try:
            if invalid_tools:
                invalid_path = MCP_CACHE_PATH.parent / "mcp_tools_invalid.json"
                invalid_path.write_text(json.dumps({"tools": invalid_tools, "refreshed_at": int(time.time())}, ensure_ascii=False, indent=2), encoding="utf-8")
                # Notify LLM about invalid tools so it can suggest fixes (non-blocking, safe)
                try:
                    from app.llm_router import LLMRouter

                    # build a compact notification payload avoiding secrets
                    items = []
                    for t in invalid_tools:
                        func = t.get("function") or {}
                        meta = t.get("mcp_meta") or {}
                        items.append({
                            "name": func.get("name"),
                            "server": meta.get("server"),
                            "reason": t.get("_validation", {}).get("reason"),
                            "description": func.get("description"),
                            "parameters_keys": list((func.get("parameters") or {}).keys()) if isinstance(func.get("parameters"), dict) else None,
                        })

                    # call LLMRouter to get suggested fixes
                    try:
                        router = LLMRouter(cfg)
                        system = "You are an assistant that suggests fixes for tool manifests. Do not expose secrets. Provide short, actionable suggestions."
                        user_msg = "The following MCP tools failed validation. For each, suggest likely fixes (one-liners) focusing on schema/name/server issues:\n" + json.dumps(items, ensure_ascii=False, indent=2)
                        try:
                            res = router.chat_messages([
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_msg},
                            ])
                            tool_store.log("mcp_validation_llm_notify", f"ok={res.ok} provider={res.provider} msg={res.text[:500]}")
                        except Exception as exc:
                            tool_store.log("mcp_validation_llm_notify_error", str(exc))
                    except Exception:
                        # best-effort: if LLMRouter fails, just log
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        tool_store.log("mcp_refresh", f"tools={len(tools)}")
        if not tools:
            # Echte Fehlermeldungen aus get_all_tools durchreichen
            _last_errs = getattr(mgr, "_last_errors", {})
            if _last_errs:
                _err_str = "; ".join(f"{k}: {v}" for k, v in _last_errs.items())
                return (
                    "mcp_refresh_tools",
                    f"MCP-Tools aktualisiert: 0. Server-Fehler: {_err_str}",
                )
            return (
                "mcp_refresh_tools",
                "MCP-Tools aktualisiert: 0 (kein Server registriert oder alle Server ohne Tools).",
            )
        return "mcp_refresh_tools", f"MCP-Tools aktualisiert: {len(tools)}"
    except Exception as exc:
        tool_store.log("mcp_refresh_error", str(exc))
        return "mcp_refresh_tools", f"MCP-Refresh fehlgeschlagen: {exc}"


def _load_cache() -> Dict[str, Any]:
    if not MCP_CACHE_PATH.exists():
        return {"tools": []}
    try:
        raw = json.loads(MCP_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("tools"), list):
            return raw
    except Exception:
        pass
    return {"tools": []}


def get_cached_mcp_tools() -> List[Dict[str, Any]]:
    _cleanup_dynamic_registry_and_cache()
    return _load_cache().get("tools", [])


def resolve_mcp_tool(tool_name: str) -> Optional[Dict[str, Any]]:
    for t in get_cached_mcp_tools():
        func = t.get("function", {}) if isinstance(t, dict) else {}
        name = str(func.get("name", "")).strip()
        if name == tool_name:
            meta = t.get("mcp_meta", {}) if isinstance(t.get("mcp_meta", {}), dict) else {}
            return {"name": name, "server": meta.get("server"), "original_name": meta.get("original_name")}
    return None


def call_mcp_tool_sync(cfg: Dict[str, Any], tool_name: str, args: Dict[str, Any]) -> Any:
    ok, msg = mcp_available()
    if not ok:
        raise RuntimeError(msg)
    from app.mcp_client import get_mcp_manager
    mgr = get_mcp_manager(cfg)  # cfg übergeben damit Server-Liste aktuell ist
    return _run_coro_sync(mgr.call_tool(tool_name, args), timeout=int(cfg.get("mcp", {}).get("timeout", 45)) + 15)


def ensure_local_server(cfg: Dict[str, Any]) -> None:
    """Entfernt den local_dynamic Server-Eintrag aus der Config falls noch vorhanden."""
    try:
        from app.config import save_config
        mcp_cfg = cfg.get("mcp", {})
        servers = mcp_cfg.get("servers", {})
        if LOCAL_SERVER_NAME in servers:
            del servers[LOCAL_SERVER_NAME]
            save_config(cfg)
    except Exception:
        pass


def _cleanup_dynamic_registry_and_cache() -> None:
    try:
        raw = _load_cache()
        tools = raw.get("tools", []) if isinstance(raw.get("tools", []), list) else []
        kept: List[Dict[str, Any]] = []
        changed = False
        for t in tools:
            if not isinstance(t, dict):
                changed = True
                continue
            func = t.get("function", {}) if isinstance(t.get("function", {}), dict) else {}
            name = str(func.get("name", "")).strip()
            if not name:
                changed = True
                continue
            kept.append(t)
        if changed:
            raw["tools"] = kept
            MCP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            MCP_CACHE_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def mcp_available() -> Tuple[bool, str]:
    try:
        from app.mcp_client import HAS_MCP, MCP_IMPORT_ERROR
        if HAS_MCP:
            return True, ""
        msg = "MCP-Python-Paket nicht installiert."
        if str(MCP_IMPORT_ERROR or "").strip():
            msg = f"{msg} Import-Fehler: {MCP_IMPORT_ERROR}"
        return False, msg
    except Exception as exc:
        return False, f"MCP nicht verfuegbar: {exc}"


def mcp_tools_as_action_schemas() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    tools_source: List[Dict[str, Any]] = get_cached_mcp_tools()

    for t in tools_source:
        if not isinstance(t, dict):
            continue
        func = t.get("function", {}) if isinstance(t.get("function", {}), dict) else {}
        name = str(func.get("name", "")).strip()
        if not name:
            continue
        schema = func.get("parameters", {})
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        out[name] = {
            "required": {},
            "optional": {},
            "allow_any": True,
            "json_schema": schema,
            "description": str(func.get("description", "")).strip(),
        }
    return out
