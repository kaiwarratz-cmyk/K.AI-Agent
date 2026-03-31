from __future__ import annotations
import re
import json
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Wir importieren diese von main, um zirkuläre Abhängigkeiten zu vermeiden 
# oder wir definieren sie hier, wenn sie klein sind.
# Da sie in main.py bleiben sollen für andere Zwecke, 
# übergeben wir die Store-Objekte oder importieren sie dynamisch.

def _profile_get_field(cfg: Dict[str, Any], field: str, memory_store_instance: Any, last_json_blob_fn: Any) -> Optional[str]:
    items = memory_store_instance.search_by_kind(kind="profile", limit=60)
    want = field.strip().lower()
    for item in items:
        blob = last_json_blob_fn(str(item.get("content", "")))
        if not isinstance(blob, dict):
            continue
        f = str(blob.get("field", "")).strip().lower()
        if f != want:
            continue
        value = str(blob.get("value", "")).strip()
        if value:
            return value
    return None

def _important_get_field(cfg: Dict[str, Any], field: str, memory_store_instance: Any, last_json_blob_fn: Any) -> Optional[str]:
    items = memory_store_instance.search_by_kind(kind="important", limit=240)
    want = field.strip().lower()
    best_value = ""
    best_score = -1.0
    for item in items:
        blob = last_json_blob_fn(str(item.get("content", "")))
        if not isinstance(blob, dict):
            continue
        f = str(blob.get("field", "")).strip().lower()
        if f != want:
            continue
        value = str(blob.get("value", "")).strip()
        if not value:
            continue
        score = float(blob.get("importance", item.get("confidence", 0.0)) or 0.0)
        if score > best_score:
            best_score = score
            best_value = value
    return best_value or None

def _recent_user_messages(cfg: Dict[str, Any], memory_store_instance: Any, last_json_blob_fn: Any, limit: int = 120) -> List[str]:
    items = memory_store_instance.search_by_kind(kind="conversation", limit=max(10, limit))
    messages: List[str] = []
    for item in reversed(items):
        blob = last_json_blob_fn(str(item.get("content", "")))
        if not isinstance(blob, dict):
            continue
        user = str(blob.get("user", "")).strip()
        if not user:
            continue
        messages.append(user)
    return messages

def _handle_sentence_recall_query(message: str, cfg: Dict[str, Any], recent_msgs_fn: Any) -> Optional[Dict[str, Any]]:
    lower = message.strip().lower()
    if not lower:
        return None
    recall_intent = bool(
        re.search(
            r"(was\s+war\s+mein\s+\d+\.?\s*(satz|nachricht)|was\s+habe\s+ich\s+vor\s+\d+\s+(saetzen|sätzen|nachrichten)\s+gesagt|wiederhole\s+die\s+letzten\s+\d+\s+(saetze|sätze|nachrichten)|zeige\s+die\s+letzten\s+\d+\s+(saetze|sätze|nachrichten))",
            lower,
            flags=re.IGNORECASE,
        )
    )
    if not recall_intent:
        return None
    msgs = recent_msgs_fn(cfg, limit=140)
    if not msgs:
        return {"ok": True, "reply": "Ich habe keine frueheren Nutzersaetze im Gedaechtnis gefunden."}

    candidates = [m for m in msgs if m.strip().lower() != lower]
    if not candidates:
        return {"ok": True, "reply": "Ich habe dazu keine vorherigen Nutzersaetze gefunden."}

    m_prev = re.search(
        r"was\s+habe\s+ich\s+vor\s+(\d+)\s+(?:saetzen|sätzen|nachrichten)\s+gesagt",
        lower,
        flags=re.IGNORECASE,
    )
    if m_prev:
        n = int(m_prev.group(1))
        if n <= 0 or n > len(candidates):
            return {"ok": True, "reply": f"Ich habe nur {len(candidates)} fruehere Nutzersaetze im Verlauf."}
        hit = candidates[-n]
        return {"ok": True, "reply": f"Vor {n} Satz/Saetzen hattest du gesagt: {hit}"}

    m_ord = re.search(
        r"was\s+war\s+mein\s+(\d+)\.?\s*(?:satz|nachricht)",
        lower,
        flags=re.IGNORECASE,
    )
    if m_ord:
        idx = int(m_ord.group(1))
        if idx <= 0 or idx > len(candidates):
            return {"ok": True, "reply": f"Im gespeicherten Verlauf habe ich {len(candidates)} Nutzersaetze."}
        hit = candidates[idx - 1]
        return {"ok": True, "reply": f"Dein Satz {idx} war: {hit}"}

    m_last = re.search(
        r"(?:wiederhole|zeige)\s+die\s+letzten\s+(\d+)\s+(?:saetze|sätze|nachrichten)",
        lower,
        flags=re.IGNORECASE,
    )
    if m_last:
        n = int(m_last.group(1))
        n = max(1, min(20, n))
        tail = candidates[-n:]
        lines = [f"Letzte {len(tail)} Nutzersaetze:"]
        for i, t in enumerate(tail, start=1):
            lines.append(f"{i}. {t}")
        return {"ok": True, "reply": "\n".join(lines)}

    return None

def _extract_secret_alias_and_value(text: str, looks_like_secret_fn: Any) -> tuple[str, str]:
    raw = str(text or "").strip()
    if not raw:
        return "", ""
    alias = ""
    m_alias = re.search(r"\balias\s+([a-zA-Z0-9_.-]{2,64})\b", raw, flags=re.IGNORECASE)
    if m_alias:
        alias = str(m_alias.group(1) or "").strip().lower()
    if not alias:
        m_for = re.search(r"\b(?:fuer|für|for)\s+([a-zA-Z0-9_.-]{2,64})\b", raw, flags=re.IGNORECASE)
        if m_for:
            alias = str(m_for.group(1) or "").strip().lower()
    value = ""
    patterns = [
        r"(?:passwort|password|api[\s_-]?key|token|secret|client_secret)\s*(?:ist|=|:)\s*\"([^\"]+)\"",
        r"(?:passwort|password|api[\s_-]?key|token|secret|client_secret)\s*(?:ist|=|:)\s*'([^']+)'",
        r"(?:passwort|password|api[\s_-]?key|token|secret|client_secret)\s*(?:ist|=|:)\s*([^\s,;]+)",
    ]
    for p in patterns:
        m = re.search(p, raw, flags=re.IGNORECASE)
        if m:
            value = str(m.group(1) or "").strip()
            break
    if not value and looks_like_secret_fn(raw):
        value = raw
    if not alias:
        hint = "secret"
        low = raw.lower()
        if "medianas" in low:
            hint = "medianas"
        elif "telegram" in low:
            hint = "telegram"
        elif "discord" in low:
            hint = "discord"
        alias = f"{hint}_cred"
    return alias[:80], value

def _handle_secret_commands(
    message: str, 
    cfg: Dict[str, Any], 
    dialog_key: str, 
    secret_store_instance: Any, 
    dialog_get_fn: Any, 
    dialog_clear_fn: Any,
    looks_like_secret_fn: Any,
    extract_fn: Any
) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip()
    if not text:
        return None
    lower = text.lower()
    pending = dialog_get_fn(dialog_key)
    if pending:
        yes = lower in {"ja", "j", "yes", "ok", "okay"}
        no = lower in {"nein", "n", "no", "abbrechen", "cancel"}
        if no:
            dialog_clear_fn(dialog_key)
            return {"ok": True, "reply": "Speichern der Zugangsdaten abgebrochen."}
        if not yes:
            return {"ok": True, "reply": "Soll ich die Zugangsdaten im Secret-Store speichern? Antworte mit: ja | nein"}
        alias = str(pending.get("alias", "") or "").strip() or "secret_cred"
        value = str(pending.get("value", "") or "").strip()
        if not value:
            dialog_clear_fn(dialog_key)
            return {"ok": True, "reply": "Kein gueltiger Secret-Wert vorhanden. Bitte erneut mit konkretem Wert senden."}
        
        existed = bool(secret_store_instance.has_alias(alias))
        stored_alias = secret_store_instance.upsert_secret(
            alias=alias,
            value=value,
            meta={"source": "user", "dialog_key": str(dialog_key or "")},
        )
        dialog_clear_fn(dialog_key)
        
        # We need the Fingerprint logic here or pass it in
        from app.secret_store import SecretStore
        fp = SecretStore.fingerprint(value)
        
        if existed:
            return {"ok": True, "reply": f"Secret unter Alias `{stored_alias}` wurde aktualisiert/ueberschrieben (fingerprint={fp})."}
        return {"ok": True, "reply": f"Secret gespeichert unter Alias `{stored_alias}` (fingerprint={fp})."}

    trigger = bool(re.search(r"\b(merke\s+dir|speicher|save|aktualisier|update|ersetz|ueberschreib|überschreib)\b", lower)) and looks_like_secret_fn(text)
    explicit_cred = bool(re.search(r"\b(zugangsdaten|credentials?)\b", lower)) and looks_like_secret_fn(text)
    if not (trigger or explicit_cred):
        return None
        
    alias, value = extract_fn(text, looks_like_secret_fn)
    if not value:
        return {"ok": True, "reply": "Ich erkenne Zugangsdaten, aber keinen konkreten Wert. Bitte sende z. B. `passwort: ...` oder `token: ...`."}
    
    # Hier müsste die Logik für "Soll ich speichern?" (Dialog) folgen, 
    # die in main.py den Dialog setzt.
    return {"_ask_save_secret": True, "alias": alias, "value": value}
