from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple


_TYPE_MAP: Dict[str, type] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
    "dict": dict,
    "object": dict,
    "list": list,
    "array": list,
}

_BASE_INTENTS = {
    "filesystem",
    "script",
    "cron",
    "send_file",
    "knowledge_or_web",
    "answer_and_save",
    "memory_query",
    "help",
    "clear_context",
    "chat",
    "unknown",
}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def load_skills_state(path: Path) -> Dict[str, Any]:
    state = _read_json(path)
    enabled = state.get("enabled", {}) if isinstance(state.get("enabled", {}), dict) else {}
    configs = state.get("configs", {}) if isinstance(state.get("configs", {}), dict) else {}
    return {"enabled": dict(enabled), "configs": dict(configs)}


def save_skills_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": state.get("enabled", {}) if isinstance(state.get("enabled", {}), dict) else {},
        "configs": state.get("configs", {}) if isinstance(state.get("configs", {}), dict) else {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def set_skill_enabled(path: Path, skill_id: str, enabled: bool) -> Dict[str, Any]:
    sid = str(skill_id or "").strip()
    state = load_skills_state(path)
    if not sid:
        return state
    state.setdefault("enabled", {})
    state["enabled"][sid] = bool(enabled)
    save_skills_state(path, state)
    return state


def set_skill_config(path: Path, skill_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    sid = str(skill_id or "").strip()
    state = load_skills_state(path)
    if not sid:
        return state
    state.setdefault("configs", {})
    state["configs"][sid] = dict(config or {})
    save_skills_state(path, state)
    return state


def _coerce_type(name: Any) -> type:
    n = str(name or "str").strip().lower()
    return _TYPE_MAP.get(n, str)


def _parse_schema_fields(raw: Any) -> Dict[str, type]:
    out: Dict[str, type] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            key = str(k or "").strip()
            if not key:
                continue
            out[key] = _coerce_type(v)
    return out


def _merge_dict(base: Dict[str, Any], add: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in (add or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _parse_secrets_required(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias", "") or "").strip()
        if not alias:
            continue
        out.append(
            {
                "alias": alias,
                "label": str(item.get("label", alias) or alias).strip(),
                "description": str(item.get("description", "") or "").strip(),
                "required": bool(item.get("required", True)),
            }
        )
    return out


def _merge_secret_specs(base: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_alias: Dict[str, Dict[str, Any]] = {}
    for item in base + extra:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias", "") or "").strip()
        if not alias:
            continue
        prev = by_alias.get(alias)
        cur = {
            "alias": alias,
            "label": str(item.get("label", alias) or alias).strip(),
            "description": str(item.get("description", "") or "").strip(),
            "required": bool(item.get("required", True)),
        }
        if prev is None:
            by_alias[alias] = cur
            continue
        if not prev.get("description") and cur.get("description"):
            prev["description"] = cur["description"]
        if not prev.get("label") and cur.get("label"):
            prev["label"] = cur["label"]
        prev["required"] = bool(prev.get("required", False) or cur.get("required", False))
    return list(by_alias.values())


def load_skill_registry(skills_dir: Path, state_path: Path) -> Dict[str, Any]:
    state = load_skills_state(state_path)
    enabled_map = state.get("enabled", {}) if isinstance(state.get("enabled", {}), dict) else {}
    cfg_map = state.get("configs", {}) if isinstance(state.get("configs", {}), dict) else {}
    reg: Dict[str, Any] = {
        "skills": [],
        "action_schemas": {},
        "handlers": {},
        "intent_kinds": {},
        "tools": [],
        "intents": [],
    }
    if not skills_dir.exists():
        return reg
    for entry in sorted(skills_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "skill.json"
        if not manifest_path.exists():
            continue
        manifest = _read_json(manifest_path)
        sid = str(manifest.get("id", entry.name) or entry.name).strip()
        if not sid:
            continue
        name = str(manifest.get("name", sid) or sid).strip()
        desc = str(manifest.get("description", "") or "").strip()
        enabled_default = bool(manifest.get("enabled_by_default", False))
        enabled = bool(enabled_map.get(sid, enabled_default))
        cfg_file = _read_json(entry / "skill_config.json")
        cfg_state = cfg_map.get(sid, {}) if isinstance(cfg_map.get(sid, {}), dict) else {}
        config = _merge_dict(cfg_file, cfg_state)

        skill_info = {
            "id": sid,
            "name": name,
            "description": desc,
            "path": str(entry),
            "enabled": enabled,
            "config": config,
            "tools": [],
        }

        tools = manifest.get("tools", []) if isinstance(manifest.get("tools", []), list) else []
        handlers = manifest.get("handlers", {}) if isinstance(manifest.get("handlers", {}), dict) else {}
        intents = manifest.get("intents", []) if isinstance(manifest.get("intents", []), list) else []
        secrets_required = _parse_secrets_required(manifest.get("secrets_required", []))
        derived_secrets: List[Dict[str, Any]] = []
        for h in handlers.values():
            if not isinstance(h, dict):
                continue
            alias = str(h.get("token_secret", "") or "").strip()
            if alias:
                derived_secrets.append(
                    {
                        "alias": alias,
                        "label": alias,
                        "description": "Secret fuer API-Authentifizierung.",
                        "required": True,
                    }
                )
        merged_secrets = _merge_secret_specs(secrets_required, derived_secrets)

        skill_info["secrets_required"] = merged_secrets
        if enabled:
            for raw_intent in intents:
                if not isinstance(raw_intent, dict):
                    continue
                iid = str(raw_intent.get("id", "") or "").strip()
                if not iid or iid not in _BASE_INTENTS:
                    continue
                reg["intents"].append({"id": iid, "description": str(raw_intent.get("description", "") or "").strip()})

        for t in tools:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id", "") or "").strip()
            kind = str(t.get("kind", "") or "").strip()
            intent = str(t.get("intent", "knowledge_or_web") or "knowledge_or_web").strip()
            if not tid or not kind or intent not in _BASE_INTENTS:
                continue
            req = _parse_schema_fields(t.get("required", {}))
            opt = _parse_schema_fields(t.get("optional", {}))
            if enabled:
                reg["action_schemas"][kind] = {"required": req, "optional": opt}
                h = handlers.get(kind, {})
                if isinstance(h, dict):
                    h2 = dict(h)
                    h2["skill_id"] = sid
                    h2["skill_name"] = name
                    h2["skill_config"] = deepcopy(config)
                    reg["handlers"][kind] = h2
                reg["intent_kinds"].setdefault(intent, [])
                if kind not in reg["intent_kinds"][intent]:
                    reg["intent_kinds"][intent].append(kind)
                reg["tools"].append(
                    {
                        "id": tid,
                        "intent": intent,
                        "kind": kind,
                        "description": str(t.get("description", "") or "").strip(),
                    }
                )
                skill_info["tools"].append({"id": tid, "intent": intent, "kind": kind})
        reg["skills"].append(skill_info)
    # de-duplicate intents by id, keep first description
    seen = set()
    uniq: List[Dict[str, str]] = []
    for it in reg["intents"]:
        iid = str(it.get("id", "") or "").strip()
        if not iid or iid in seen:
            continue
        seen.add(iid)
        uniq.append({"id": iid, "description": str(it.get("description", "") or "").strip()})
    reg["intents"] = uniq
    return reg


def skill_snapshot_for_api(registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in registry.get("skills", []) if isinstance(registry.get("skills", []), list) else []:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "id": str(s.get("id", "") or ""),
                "name": str(s.get("name", "") or ""),
                "description": str(s.get("description", "") or ""),
                "enabled": bool(s.get("enabled", False)),
                "path": str(s.get("path", "") or ""),
                "tools": list(s.get("tools", [])) if isinstance(s.get("tools", []), list) else [],
                "secrets_required": list(s.get("secrets_required", []))
                if isinstance(s.get("secrets_required", []), list)
                else [],
                "config": dict(s.get("config", {})) if isinstance(s.get("config", {}), dict) else {},
            }
        )
    return out


def skill_tool_lines(registry: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for t in registry.get("tools", []) if isinstance(registry.get("tools", []), list) else []:
        if not isinstance(t, dict):
            continue
        out.append(
            (
                str(t.get("id", "") or "").strip(),
                str(t.get("intent", "") or "").strip(),
                str(t.get("kind", "") or "").strip(),
            )
        )
    return out
