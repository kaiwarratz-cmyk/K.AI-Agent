"""
MCP Client für K.AI
===================
Stellt get_mcp_manager(), HAS_MCP und MCP_IMPORT_ERROR bereit.
Liest Server-Konfiguration aus cfg["mcp"]["servers"].

Tool-Format (kompatibel mit mcp_tools.py):
{
    "function": {
        "name": "<server_alias>__<original_tool_name>",
        "description": "...",
        "parameters": {...}   # JSON-Schema
    },
    "mcp_meta": {
        "server": "<server_key>",
        "original_name": "<original_tool_name>"
    }
}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# ── Windows: CREATE_NO_WINDOW für alle asyncio-Subprozesse ─────────────────
# Verhindert sichtbare Konsolenfenster und "Wie möchten Sie diese Datei öffnen"-Dialoge
# wenn MCP-Server (z.B. webpeel mit Playwright) Child-Prozesse spawnen.
if sys.platform == "win32":
    try:
        import ctypes as _ctypes
        # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        _ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except Exception:
        pass
    try:
        # Monkey-patch asyncio ProactorEventLoop: immer CREATE_NO_WINDOW setzen
        _CREATE_NO_WINDOW = 0x08000000
        _orig_subprocess_exec = asyncio.ProactorEventLoop.subprocess_exec

        async def _patched_subprocess_exec(self, protocol_factory, *args, **kwargs):
            cf = kwargs.get("creationflags") or 0
            kwargs["creationflags"] = cf | _CREATE_NO_WINDOW
            return await _orig_subprocess_exec(self, protocol_factory, *args, **kwargs)

        asyncio.ProactorEventLoop.subprocess_exec = _patched_subprocess_exec
    except Exception:
        pass

# ── MCP-Import Guard ───────────────────────────────────────────────────────
HAS_MCP: bool = False
MCP_IMPORT_ERROR: Optional[str] = None

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except Exception as _exc:
    MCP_IMPORT_ERROR = str(_exc)
    _log.warning("MCP-Paket nicht importierbar – MCP deaktiviert. Fehler: %s", _exc)

# ── Singleton ──────────────────────────────────────────────────────────────
_mcp_manager_instance: Optional["MCPManager"] = None


def get_mcp_manager(cfg: Optional[Dict[str, Any]] = None) -> "MCPManager":
    """Gibt die globale MCPManager-Instanz zurück (lazy-init)."""
    global _mcp_manager_instance
    if _mcp_manager_instance is None:
        _mcp_manager_instance = MCPManager(cfg or {})
    elif cfg is not None:
        # Config-Update: Server-Liste neu laden
        _mcp_manager_instance._load_servers(cfg)
    return _mcp_manager_instance


# ── Hilfsfunktion: Tool-Name sicher machen ────────────────────────────────
def _safe_name(s: str) -> str:
    """Ersetzt Sonderzeichen durch Unterstriche für sichere Tool-Namen."""
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)


class MCPManager:
    """
    Verwaltet mehrere MCP stdio-Server aus der K.AI-Config.
    Server-Konfiguration: cfg["mcp"]["servers"] = {
        "server_key": {
            "type": "stdio",
            "command": "node",
            "args": ["path/to/server.js"],
            "env": {},
            "cwd": "..."   # optional
        }
    }
    """

    def __init__(self, cfg: Dict[str, Any]):
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._load_servers(cfg)

    def _load_servers(self, cfg: Dict[str, Any]) -> None:
        """Lädt Server-Definitionen aus der Config."""
        mcp_cfg = cfg.get("mcp", {}) if isinstance(cfg, dict) else {}
        servers_raw = mcp_cfg.get("servers", {})
        if not isinstance(servers_raw, dict):
            self._servers = {}
            return
        loaded: Dict[str, Dict[str, Any]] = {}
        for key, srv in servers_raw.items():
            if not isinstance(srv, dict):
                continue
            command = str(srv.get("command", "")).strip()
            if not command:
                continue
            args = srv.get("args", [])
            if not isinstance(args, list):
                args = []
            loaded[key] = {
                "command": command,
                "args": [str(a) for a in args],
                "env": srv.get("env") or None,
                "cwd": str(srv.get("cwd", "")).strip() or None,
            }
        self._servers = loaded

    # ── Tool Discovery ─────────────────────────────────────────────────────

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """Fragt alle konfigurierten Server nach ihren Tools (parallel)."""
        if not HAS_MCP or not self._servers:
            return []
        srv_keys = list(self._servers.keys())
        tasks = [
            self._fetch_tools_from_server(srv_key, self._servers[srv_key])
            for srv_key in srv_keys
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        tools: List[Dict[str, Any]] = []
        self._last_errors: Dict[str, str] = {}
        for srv_key, res in zip(srv_keys, results):
            if isinstance(res, list):
                tools.extend(res)
            elif isinstance(res, Exception):
                # Sub-Exception aus ExceptionGroup/TaskGroup extrahieren für echten Fehlertext
                _cause = res
                if hasattr(res, "exceptions") and res.exceptions:
                    _cause = res.exceptions[0]
                elif res.__cause__ is not None:
                    _cause = res.__cause__
                _err_msg = f"{type(_cause).__name__}: {_cause}"
                self._last_errors[srv_key] = _err_msg
                _log.warning("MCP-Server '%s' Fehler: %s", srv_key, _err_msg)
        return tools

    async def _fetch_tools_from_server(
        self,
        srv_key: str,
        srv_cfg: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Verbindet sich mit einem stdio-Server und listet dessen Tools.
        Wirft Exception bei Fehler — wird von asyncio.gather(return_exceptions=True) gefangen."""
        if not HAS_MCP:
            return []
        import shutil as _shutil, sys as _sys
        _cmd = srv_cfg["command"]
        _args = list(srv_cfg["args"])
        # Windows: .cmd-Dateien können nicht direkt von asyncio gestartet werden
        # → shutil.which("npx") gibt auf Windows "npx.cmd" zurück → MUSS über cmd.exe /c
        if _sys.platform == "win32":
            _which = _shutil.which(_cmd)
            if _which:
                _cmd = _which  # z.B. "npx" → "C:\...\npx.cmd"
            elif not Path(_cmd).is_absolute():
                _node_dir = Path(r"C:\Program Files\nodejs")
                for _ext in ["", ".cmd", ".exe"]:
                    _candidate = _node_dir / (_cmd + _ext)
                    if _candidate.exists():
                        _cmd = str(_candidate)
                        break
            # .cmd/.bat Dateien: über cmd.exe /c starten
            if str(_cmd).lower().endswith(".cmd") or str(_cmd).lower().endswith(".bat"):
                _args = ["/c", _cmd] + _args
                _cmd = "cmd.exe"
        params = StdioServerParameters(
            command=_cmd,
            args=_args,
            env=srv_cfg.get("env"),
            cwd=srv_cfg.get("cwd"),
        )
        # stderr → NUL um Windows-Dialoge durch unkontrollierte Prozessausgaben zu verhindern
        import io as _io
        _errlog = _io.open(os.devnull, "w", encoding="utf-8")
        async with asyncio.timeout(90):
            async with stdio_client(params, errlog=_errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    out: List[Dict[str, Any]] = []
                    safe_key = _safe_name(srv_key)
                    for tool in result.tools:
                        orig_name = str(tool.name or "").strip()
                        if not orig_name:
                            continue
                        # Eindeutiger Name: <server>__<tool>
                        full_name = f"{safe_key}__{orig_name}"
                        # JSON-Schema aus inputSchema extrahieren
                        schema = {}
                        raw_schema = getattr(tool, "inputSchema", None)
                        if isinstance(raw_schema, dict):
                            schema = raw_schema
                        elif raw_schema is not None:
                            try:
                                schema = dict(raw_schema)
                            except Exception:
                                pass
                        out.append({
                            "function": {
                                "name": full_name,
                                "description": str(tool.description or "").strip(),
                                "parameters": schema,
                            },
                            "mcp_meta": {
                                "server": srv_key,
                                "original_name": orig_name,
                            },
                        })
                    return out

    # ── Tool Execution ─────────────────────────────────────────────────────

    async def call_tool(
        self,
        full_tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """Führt ein Tool auf dem zugehörigen Server aus."""
        if not HAS_MCP:
            return "Fehler: MCP nicht verfügbar."

        # Namen zurück zu original_name + server auflösen
        srv_key, orig_name = self._resolve_tool_name(full_tool_name)
        if not srv_key:
            return f"Fehler: Kein Server für Tool '{full_tool_name}' gefunden."

        srv_cfg = self._servers.get(srv_key)
        if not srv_cfg:
            return f"Fehler: Server '{srv_key}' nicht in der Config."

        try:
            import shutil as _shutil, sys as _sys
            _call_cmd = srv_cfg["command"]
            _call_args = list(srv_cfg["args"])
            # Windows: shutil.which("npx") gibt "npx.cmd" zurück → über cmd.exe /c starten
            if _sys.platform == "win32":
                _which2 = _shutil.which(_call_cmd)
                if _which2:
                    _call_cmd = _which2  # z.B. "npx" → "C:\...\npx.cmd"
                elif not Path(_call_cmd).is_absolute():
                    _node_dir = Path(r"C:\Program Files\nodejs")
                    for _ext in ["", ".cmd", ".exe"]:
                        _candidate = _node_dir / (_call_cmd + _ext)
                        if _candidate.exists():
                            _call_cmd = str(_candidate)
                            break
                if str(_call_cmd).lower().endswith(".cmd") or str(_call_cmd).lower().endswith(".bat"):
                    _call_args = ["/c", _call_cmd] + _call_args
                    _call_cmd = "cmd.exe"
            params = StdioServerParameters(
                command=_call_cmd,
                args=_call_args,
                env=srv_cfg.get("env"),
                cwd=srv_cfg.get("cwd"),
            )
            async with asyncio.timeout(60):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(orig_name, arguments)
                        parts = [
                            content.text
                            for content in result.content
                            if hasattr(content, "text") and content.text
                        ]
                        return "\n".join(parts) if parts else "Tool ausgeführt (keine Ausgabe)."
        except Exception as exc:
            return f"Fehler bei Tool-Ausführung '{full_tool_name}' auf Server '{srv_key}': {exc}"

    def _resolve_tool_name(self, full_name: str):
        """Löst 'safekey__orig_name' → (srv_key, orig_name) auf."""
        if "__" in full_name:
            safe_key, orig_name = full_name.split("__", 1)
            # Rück-Mapping: safe_key → original server_key
            for srv_key in self._servers:
                if _safe_name(srv_key) == safe_key:
                    return srv_key, orig_name
        # Fallback: server_key direkt aus Cache nachschlagen
        return None, full_name
