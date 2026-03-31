from __future__ import annotations

from typing import Dict, Optional

import httpx


def _normalize_channel_id(channel_id: str) -> str:
    parts = [p.strip() for p in str(channel_id or "").split("/") if p.strip()]
    if not parts:
        return ""
    return parts[-1]


def healthcheck(enabled: bool, token: str, channel_id: Optional[str] = None, timeout_sec: int = 10) -> Dict[str, str | bool]:
    token_set = bool(token)
    if not enabled:
        return {"enabled": False, "token_set": token_set, "ok": False, "message": "Discord ist deaktiviert."}
    if not token_set:
        return {"enabled": True, "token_set": False, "ok": False, "message": "Discord Token fehlt."}
    try:
        headers = {"Authorization": f"Bot {token}"}
        with httpx.Client(timeout=timeout_sec, trust_env=False) as client:
            res = client.get("https://discord.com/api/v10/users/@me", headers=headers)
            res.raise_for_status()
            data = res.json()
            user = data.get("username", "")
            suffix = f" @{user}" if user else ""
            normalized_channel = _normalize_channel_id(channel_id or "")
            if normalized_channel:
                channel_res = client.get(f"https://discord.com/api/v10/channels/{normalized_channel}", headers=headers)
                if channel_res.status_code >= 400:
                    return {
                        "enabled": True,
                        "token_set": True,
                        "ok": False,
                        "message": f"Discord Bot ok{suffix}, aber Channel nicht erreichbar ({normalized_channel}).",
                    }
            return {"enabled": True, "token_set": True, "ok": True, "message": f"Discord erreichbar{suffix}."}
    except Exception as exc:
        return {"enabled": True, "token_set": True, "ok": False, "message": f"Discord Fehler: {exc}"}
