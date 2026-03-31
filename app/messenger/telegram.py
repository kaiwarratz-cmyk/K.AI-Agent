from __future__ import annotations

from typing import Dict

import httpx


def healthcheck(enabled: bool, token: str, timeout_sec: int = 10) -> Dict[str, str | bool]:
    token_set = bool(token)
    if not enabled:
        return {"enabled": False, "token_set": token_set, "ok": False, "message": "Telegram ist deaktiviert."}
    if not token_set:
        return {"enabled": True, "token_set": False, "ok": False, "message": "Telegram Token fehlt."}
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with httpx.Client(timeout=timeout_sec, trust_env=False) as client:
            res = client.get(url)
            res.raise_for_status()
            data = res.json()
        if not data.get("ok"):
            return {"enabled": True, "token_set": True, "ok": False, "message": "Telegram API meldet Fehler."}
        username = (data.get("result") or {}).get("username", "")
        suffix = f" @{username}" if username else ""
        return {"enabled": True, "token_set": True, "ok": True, "message": f"Telegram erreichbar{suffix}."}
    except Exception as exc:
        return {"enabled": True, "token_set": True, "ok": False, "message": f"Telegram Fehler: {exc}"}
