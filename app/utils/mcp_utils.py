from __future__ import annotations
from typing import Any, Dict, Tuple
from app.tool_engine import tool_store
from app.config import save_config

def _mcp_register_server(cfg: Dict[str, Any], action: Dict[str, Any]) -> Tuple[str, str]:
    """Registriert einen neuen MCP-Server in der Konfiguration."""
    name = str(action.get("name", "")).strip()
    command = str(action.get("command", "")).strip()
    if not name or not command:
        return "mcp_register_server", "name/command fehlen."
    
    args = action.get("args", [])
    if not isinstance(args, list):
        args = []
        
    env = action.get("env", {})
    if not isinstance(env, dict):
        env = {}
        
    srv_type = str(action.get("type", "stdio")).strip() or "stdio"
    cwd = str(action.get("cwd", "")).strip() or None
    
    mcp = cfg.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        mcp = {}
        cfg["mcp"] = mcp
        
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        servers = {}
        mcp["servers"] = servers
        
    entry: Dict[str, Any] = {
        "type": srv_type,
        "command": command,
        "args": args,
        "env": env
    }
    if cwd:
        entry["cwd"] = cwd
        
    servers[name] = entry
    save_config(cfg)
    tool_store.log("mcp_register", f"name={name} command={command}")
    return "mcp_register_server", f"MCP-Server registriert: {name}"

def _mcp_remove_server(cfg: Dict[str, Any], action: Dict[str, Any]) -> Tuple[str, str]:
    """Entfernt einen MCP-Server aus der Konfiguration."""
    name = str(action.get("name", "")).strip()
    if not name:
        return "mcp_remove_server", "name fehlt."
        
    mcp = cfg.get("mcp", {})
    if not isinstance(mcp, dict):
        return "mcp_remove_server", "Keine MCP-Konfiguration vorhanden."
        
    servers = mcp.get("servers", {})
    if not isinstance(servers, dict) or name not in servers:
        return "mcp_remove_server", f"MCP-Server nicht gefunden: {name}"
        
    servers.pop(name, None)
    save_config(cfg)
    tool_store.log("mcp_remove", f"name={name}")
    return "mcp_remove_server", f"MCP-Server entfernt: {name}"
