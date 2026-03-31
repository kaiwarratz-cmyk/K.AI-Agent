from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"


def _deep_merge(base: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for key, val in raw.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _default_config() -> Dict[str, Any]:
    return {
        "security": {"active_role": "user", "execution_mode": "unrestricted", "secrets_db_path": "data\\secrets.db"},
        "filesystem": {"full_access": False, "delete_to_trash": True},
        "llm": {
            "active_provider_id": "openai",
            "active_model": "gpt-4o-mini",
            "temperature": 0.2,
            "retry_policy": {
                "defaults": {
                    "max_attempts": 3,
                    "base_delay_seconds": 1.0,
                    "backoff_factor": 2.0,
                    "max_delay_seconds": 8.0,
                    "jitter_ratio": 0.2,
                    "retry_on_status": [408, 409, 425, 429, 500, 502, 503, 504],
                    "retry_on_network_errors": True,
                },
                "channels": {
                    "chat": {"max_attempts": 3},
                    "json": {"max_attempts": 3},
                    "stream": {"max_attempts": 2, "max_delay_seconds": 6.0},
                },
                "providers": {},
            },
        },
        "providers": {},
        "messenger": {
            "reply_timeout_sec": 600,
            "telegram": {
                "enabled": False,
                "token": "",
                "require_prefix": False,
                "command_prefix": "/kaia",
                "dm_policy": "open",
                "group_policy": "open",
                "allow_from": [],
            },
            "discord": {
                "enabled": False,
                "token": "",
                "channel_id": "",
                "require_prefix": True,
                "command_prefix": "/botname",
                "gateway_enabled": True,
                "dm_policy": "open",
                "group_policy": "open",
                "allow_from": ["*"],
            },
            "session_memory_enabled": True,
        },
        "tts": {"enabled": False, "voice": "de-DE-ConradNeural", "mode": "reply_audio"},
        "workspace": "data\\workspace",
        "memory": {
            "db_path": "data\\chroma_db",
            "use_global_conversation_fallback": False,
            "episode_reflection_enabled": True,
            "session_summary_enabled": True,
            "session_summary_max_highlights": 18,
            "session_summary_prompt_chars": 420,
            "auto_llm_enabled": False,
            "auto_llm_min_confidence": 0.82,
            "auto_llm_max_chars": 220,
        },
        "routing": {
            "llm_first": True,
            "deterministic_fallback": True,
            "heuristics_enabled": False,
            "fallback_confidence_threshold": 0.62,
            "llm_abstain_enabled": True,
            "domain_min_confidence": 0.58,
            "intent_thresholds": {
                "filesystem": 0.64,
                "script": 0.68,
                "cron": 0.66,
                "answer_and_save": 0.66,
                "memory_query": 0.62,
                "help": 0.68,
                "clear_context": 0.68,
                "chat": 0.5,
                "unknown": 0.0,
            },
        },
        "self_improve": {
            "enabled": True,
            "scan_interval_sec": 300,
            "deep_check_interval_sec": 1800,
            "cooldown_sec": 900,
            "auto_execute": False,
        },
        "logging": {
            "enabled": True,
            "verbose": True,
            "audit_log_path": "data\\logs\\audit.log",
        },
        "mcp": {
            "timeout": 180, # Timeout für externe MCP-Tools (Netzwerk/Suche)
            "cache_ttl_sec": 300,
            "local_server_enabled": True,
            "servers": {},
            "registry_sources": [
                {
                    "id": "mcp_registry_official",
                    "type": "mcp_registry",
                    "name": "Official MCP Registry",
                    "base_url": "https://registry.modelcontextprotocol.io",
                    "enabled": True,
                },
                {
                    "id": "github",
                    "type": "github",
                    "name": "GitHub (topic:mcp-server)",
                    "base_url": "https://api.github.com",
                    "enabled": True,
                },
            ],
        },
        "web_server": {
            "host": "127.0.0.1",
            "port": 8000,
        },
        "execution_plane": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8765,
            "auth_token": "",
            "auto_start": True,
            "show_console": False,
            "request_timeout_sec": 1800,
            "fallback_to_local": True,
        },
        "cli_core": {
            "enabled": True,
            "prefer_self_building": True,
            "strict_minimal": True,
            "allow_legacy_fallback": False,
            "max_iterations": 50,
            "max_step_timeout_sec": 600,
            "llm_timeout_sec": 120, # Timeout für LLM API-Anfragen
            "use_smart_context": True, # Intelligenter Memory-Recall
            "base_tools": [
                "list_entries",
                "read_file",
                "write_file",
                "script_exec",
                "script_create",
                "mcp_refresh_tools",
            ],
        },
        "tools": {
            "dynamic_timeout_sec": 120,
            "max_output_chars": 8000,
            "tool_output_cap_chars": 25000,
        },
    }


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        cfg = _default_config()
        save_config(cfg)
        return cfg
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    merged = _deep_merge(_default_config(), raw if isinstance(raw, dict) else {})
    mode = str(merged.get("security", {}).get("execution_mode", "unrestricted")).lower()
    if mode not in {"deny", "unrestricted"}:
        merged.setdefault("security", {})
        merged["security"]["execution_mode"] = "unrestricted"
    return merged


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
