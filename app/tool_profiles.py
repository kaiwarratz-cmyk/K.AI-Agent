from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parent.parent
PROVIDERS_DIR = ROOT_DIR / "tool_profiles" / "providers"
MODELS_DIR = ROOT_DIR / "tool_profiles" / "models"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _model_matches(rule: Dict[str, Any], model: str) -> bool:
    pat = str(rule.get("model", "") or "").strip().lower()
    if not pat:
        return False
    m = str(model or "").strip().lower()
    mode = str(rule.get("match", "exact") or "exact").strip().lower()
    if mode == "prefix":
        return m.startswith(pat)
    if mode == "contains":
        return pat in m
    return m == pat


def resolve_tool_profile(provider_type: str, model: str, provider_id: str = "") -> Dict[str, Any]:
    ptype = str(provider_type or "").strip().lower()
    mdl = str(model or "").strip()
    pid = str(provider_id or "").strip().lower()

    base: Dict[str, Any] = {
        "provider_type": ptype,
        "model": mdl,
        "strategy_order": ["json_schema", "json_text"],
        "native_tools": {"enabled": False},
    }

    # Provider-id profile takes precedence over generic provider-type profile.
    provider_files: List[Path] = []
    if pid:
        provider_files.append(PROVIDERS_DIR / f"{pid}.json")
    if ptype:
        provider_files.append(PROVIDERS_DIR / f"{ptype}.json")
    for pfile in provider_files:
        if not pfile.exists():
            continue
        pobj = _read_json(pfile)
        if isinstance(pobj, dict):
            base.update({k: v for k, v in pobj.items() if k not in {"version"}})

    best: Dict[str, Any] = {}
    best_score = -1
    if MODELS_DIR.exists():
        for mf in MODELS_DIR.glob("*.json"):
            robj = _read_json(mf)
            if not robj:
                continue
            if not _model_matches(robj, mdl):
                continue
            mode = str(robj.get("match", "exact") or "exact").strip().lower()
            score = {"exact": 3, "prefix": 2, "contains": 1}.get(mode, 0)
            if score > best_score:
                best_score = score
                best = robj
    if best:
        base.update({k: v for k, v in best.items() if k not in {"version", "match", "model"}})

    order = base.get("strategy_order", []) if isinstance(base.get("strategy_order", []), list) else []
    norm: List[str] = []
    for s in order:
        x = str(s or "").strip().lower()
        if x and x not in norm:
            norm.append(x)
    if not norm:
        norm = ["json_schema", "json_text"]
    base["strategy_order"] = norm
    return base
