from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import random
import re
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import httpx

# Thread-lokaler Retry-Notify-Callback.
# Kann von außen gesetzt werden (z.B. react loop in main.py) um bei LLM-Netzwerkfehlern
# eine Nutzermeldung über alle Kanäle zu senden.
# Signatur: fn(reason: str, delay_sec: float, retry_at: str, provider: str, model: str)
_retry_notify_local = threading.local()


def set_retry_notify_cb(fn: Optional[Callable]) -> None:
    """Setzt den Retry-Notify-Callback für den aktuellen Thread."""
    _retry_notify_local.cb = fn


def clear_retry_notify_cb() -> None:
    """Entfernt den Callback für den aktuellen Thread."""
    _retry_notify_local.cb = None


def _fire_retry_notify(reason: str, delay_sec: float, provider: str, model: str) -> None:
    cb = getattr(_retry_notify_local, "cb", None)
    if not callable(cb):
        return
    try:
        retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_sec)).strftime("%H:%M:%S")
        cb(reason=reason, delay_sec=delay_sec, retry_at=retry_at, provider=provider, model=model)
    except Exception:
        pass


@dataclass
class LLMResult:
    ok: bool
    provider: str
    model: str
    text: str
    message: str


class LLMRouterError(RuntimeError):
    pass


class LLMRouter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._cache_stats_enabled = True  # Für Logging

    @property
    def _timeout(self) -> int:
        """Gibt den konfigurierten LLM-Timeout zurück (Default: 120s)."""
        core_cfg = self.config.get("cli_core", {}) if isinstance(self.config.get("cli_core", {}), dict) else {}
        # Wir unterstützen auch das alte Format falls vorhanden
        if "llm_timeout_sec" not in core_cfg:
            llm_cfg = self.config.get("llm", {})
            return int(llm_cfg.get("request_timeout_sec", 120))
        return int(core_cfg.get("llm_timeout_sec", 120))

    def _should_use_prompt_caching(self, model: str) -> bool:
        """Prüft ob Prompt Caching für dieses Modell aktiviert werden soll."""
        # Config-Check
        llm_cfg = self.config.get("llm", {})
        caching_cfg = llm_cfg.get("prompt_caching", {})
        
        # Manuell deaktiviert?
        if caching_cfg.get("enabled") == False:
            return False
        
        # Nur Claude 3+ unterstützt Caching
        model_lower = model.lower()
        if not model_lower.startswith("claude"):
            return False
        
        # Claude 2.x unterstützt kein Caching
        if "claude-2" in model_lower:
            return False
        
        return True
    
    def _log_cache_stats(self, usage: Dict[str, Any]) -> None:
        """Loggt Cache-Statistiken wenn aktiviert."""
        if not self._cache_stats_enabled:
            return
        
        llm_cfg = self.config.get("llm", {})
        caching_cfg = llm_cfg.get("prompt_caching", {})
        
        if not caching_cfg.get("log_stats", True):
            return
        
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        input_tokens = usage.get("input_tokens", 0)
        
        if cache_creation > 0:
            print(f"[CACHE] Cache Write: {cache_creation} tokens")
        if cache_read > 0:
            print(f"[CACHE] Cache Hit! Read: {cache_read} tokens")
        if input_tokens > 0:
            print(f"[CACHE] Input: {input_tokens} tokens")

    def get_relevant_context_for_llm(
        self, 
        memory_store, 
        secret_store, 
        query: str = "",
        max_facts: int = 10,
        max_tokens: int = 300,
        min_similarity: float = 0.65
    ) -> Dict[str, Any]:
        """
        Holt relevante Fakten aus dem MemoryStore mit Query-basierter Relevanzfilterung.
        Nutzt Hybrid-Search (Vektor + Keyword) falls verfuegbar.
        """
        import re
        
        # Verwende Query fuer Suche (falls vorhanden)
        if query and memory_store:
            try:
                if hasattr(memory_store, 'search_hybrid'):
                    facts = memory_store.search_hybrid(
                        query=query[:200],  # Limitiere Query-Laenge
                        limit=max_facts * 2,  # Hole mehr fuer Post-Filtering
                        min_similarity=min_similarity
                    )
                elif hasattr(memory_store, 'search'):
                    facts = memory_store.search(
                        query=query[:200],
                        limit=max_facts * 2,
                        min_similarity=min_similarity
                    )
                else:
                    facts = []
            except Exception:
                # Fallback: Keine Query-basierte Suche
                facts = []
        else:
            facts = []
        
        # Fallback bei zu wenig Ergebnissen: Erweitere Similarity-Threshold
        if len(facts) < 3 and query and min_similarity > 0.5:
            try:
                facts = memory_store.search(
                    query=query[:200],
                    limit=max_facts * 2,
                    min_similarity=0.5
                )
            except Exception:
                facts = []
        
        result_facts = []
        secret_candidates = []
        secret_patterns = [
            r'(passwort|password|api[_-]?key|token|secret)[\s:=]+[\w\-\d]{6,}',
        ]
        
        current_tokens = 0
        seen_hashes = set()
        
        for fact in facts:
            content = fact.get('content', '')
            
            # Konvertiere zu String
            if isinstance(content, str):
                text = content
            else:
                try:
                    import json
                    text = json.dumps(content, ensure_ascii=False)
                except Exception:
                    text = str(content)
            
            # Skip leere oder sehr kurze Facts
            if not text or len(text) < 10:
                continue
            
            # Deduplizierung via Content-Hash
            import hashlib
            content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            
            # Token-Budget pruefen (grob: 4 chars = 1 token)
            fact_tokens = len(text) // 4
            if current_tokens + fact_tokens > max_tokens:
                break
            
            # Secret-Erkennung (nur bei neuen Facts)
            for pat in secret_patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    val = m.group(0)
                    if secret_store and hasattr(secret_store, 'has_alias'):
                        if not secret_store.has_alias(val):
                            secret_candidates.append({'value': val, 'source': text[:100]})
            
            result_facts.append(text)
            current_tokens += fact_tokens
            
            if len(result_facts) >= max_facts:
                break
        
        return {
            'facts': result_facts,
            'secret_candidates': secret_candidates,
            'token_usage': current_tokens
        }
    
    def get_relevant_context_for_llm_fallback(self, memory_store, secret_store, max_facts: int = 20) -> Dict[str, Any]:
        """
        Fallback-Wrapper fuer Abwaertskompatibilitaet.
        Ruft neue Methode mit Default-Parametern auf.
        """
        return self.get_relevant_context_for_llm(
            memory_store=memory_store,
            secret_store=secret_store,
            query="",  # Keine Query = Fallback auf alle Facts
            max_facts=max_facts,
            max_tokens=300,
            min_similarity=0.0  # Niedrig fuer Kompatibilitaet
        )

    def _llm_config(self) -> Dict[str, Any]:
        return self.config.get("llm", {})

    def _provider_config(self, provider_id: str) -> Dict[str, Any]:
        return self.config.get("providers", {}).get(provider_id, {})

    @staticmethod
    def _provider_enabled(provider_cfg: Dict[str, Any]) -> bool:
        if isinstance(provider_cfg, dict) and "enabled" in provider_cfg:
            return bool(provider_cfg.get("enabled"))
        return True

    @staticmethod
    def _provider_requires_api_key(provider_cfg: Dict[str, Any]) -> bool:
        if not isinstance(provider_cfg, dict):
            return True
        val = provider_cfg.get("api_key_required")
        if isinstance(val, bool):
            return bool(val)
        val = provider_cfg.get("allow_empty_api_key")
        if isinstance(val, bool):
            return not bool(val)
        return True

    def _provider_chain(self) -> list[str]:
        llm = self._llm_config()
        active = str(llm.get("active_provider_id", "")).strip()
        configured_fallbacks = llm.get("fallback_provider_ids", [])
        order: list[str] = []
        if active:
            order.append(active)
        if isinstance(configured_fallbacks, list):
            for pid in configured_fallbacks:
                p = str(pid or "").strip()
                if p and p not in order:
                    order.append(p)
        # Kein automatisches Hinzufügen aller Provider — nur aktiver + explizite Fallbacks
        out: list[str] = []
        for pid in order:
            cfg = self._provider_config(pid)
            if not cfg:
                continue
            if not self._provider_enabled(cfg):
                continue
            if self._provider_requires_api_key(cfg) and not str(cfg.get("api_key", "")).strip():
                continue
            if not str(cfg.get("base_url", "")).strip():
                continue
            out.append(pid)
        return out

    def _provider_runtime(self, provider_id: str) -> tuple[Dict[str, Any], str, str]:
        llm = self._llm_config()
        provider_cfg = self._provider_config(provider_id)
        if not provider_cfg:
            raise LLMRouterError(f"Provider '{provider_id}' ist nicht konfiguriert.")
        if not self._provider_enabled(provider_cfg):
            raise LLMRouterError(f"Provider '{provider_id}' ist deaktiviert.")
        model = str(provider_cfg.get("default_model") or llm.get("active_model") or "unknown")
        provider_type = str(provider_cfg.get("type", "openai_compatible"))
        return provider_cfg, model, provider_type

    @staticmethod
    def _to_int(value: Any, default: int, minimum: int = 1, maximum: int = 30) -> int:
        try:
            out = int(value)
        except Exception:
            out = default
        return max(minimum, min(maximum, out))

    @staticmethod
    def _to_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 120.0) -> float:
        try:
            out = float(value)
        except Exception:
            out = default
        return max(minimum, min(maximum, out))

    @staticmethod
    def _as_status_set(value: Any, fallback: set[int]) -> set[int]:
        if not isinstance(value, list):
            return fallback
        out: set[int] = set()
        for item in value:
            try:
                status = int(item)
            except Exception:
                continue
            if 100 <= status <= 599:
                out.add(status)
        return out or fallback

    def _retry_policy(self, channel: str, provider_id: str) -> Dict[str, Any]:
        llm = self._llm_config()
        retry_cfg = llm.get("retry_policy", {}) if isinstance(llm.get("retry_policy", {}), dict) else {}
        defaults_cfg = retry_cfg.get("defaults", {}) if isinstance(retry_cfg.get("defaults", {}), dict) else {}
        channels_cfg = retry_cfg.get("channels", {}) if isinstance(retry_cfg.get("channels", {}), dict) else {}
        providers_cfg = retry_cfg.get("providers", {}) if isinstance(retry_cfg.get("providers", {}), dict) else {}
        channel_cfg = channels_cfg.get(channel, {}) if isinstance(channels_cfg.get(channel, {}), dict) else {}
        provider_cfg = providers_cfg.get(provider_id, {}) if isinstance(providers_cfg.get(provider_id, {}), dict) else {}
        provider_channel_cfg = (
            provider_cfg.get(channel, {}) if isinstance(provider_cfg.get(channel, {}), dict) else {}
        )

        merged: Dict[str, Any] = {}
        for block in (defaults_cfg, channel_cfg, provider_channel_cfg):
            merged.update(block)

        fallback_retry_status = {408, 409, 425, 429, 500, 502, 503, 504}
        return {
            "max_attempts": self._to_int(merged.get("max_attempts"), default=3, minimum=1, maximum=12),
            "base_delay_seconds": self._to_float(merged.get("base_delay_seconds"), default=1.0, minimum=0.0, maximum=30.0),
            "backoff_factor": self._to_float(merged.get("backoff_factor"), default=2.0, minimum=1.0, maximum=5.0),
            "max_delay_seconds": self._to_float(merged.get("max_delay_seconds"), default=8.0, minimum=0.0, maximum=120.0),
            "jitter_ratio": self._to_float(merged.get("jitter_ratio"), default=0.2, minimum=0.0, maximum=1.0),
            "retry_on_status": self._as_status_set(merged.get("retry_on_status"), fallback_retry_status),
            "retry_on_network_errors": bool(merged.get("retry_on_network_errors", True)),
        }

    def ping(self) -> Dict[str, Any]:
        llm = self._llm_config()
        provider_id = llm.get("active_provider_id", "unknown")
        model = llm.get("active_model", "unknown")
        provider_cfg = self._provider_config(provider_id)
        provider_type = provider_cfg.get("type", "unknown")
        requires_key = self._provider_requires_api_key(provider_cfg)
        has_key = bool(str(provider_cfg.get("api_key", "") or "").strip())
        if not provider_cfg:
            return {
                "ok": False,
                "provider": provider_id,
                "model": model,
                "message": "Provider nicht konfiguriert.",
            }
        if not self._provider_enabled(provider_cfg):
            return {
                "ok": False,
                "provider": provider_id,
                "model": model,
                "provider_type": provider_type,
                "message": "Provider deaktiviert.",
            }
        if requires_key and not has_key:
            return {
                "ok": False,
                "provider": provider_id,
                "model": model,
                "provider_type": provider_type,
                "message": "Kein API Key gesetzt. Live-Test nicht moeglich.",
            }
        return {
            "ok": True,
            "provider": provider_id,
            "model": model,
            "provider_type": provider_type,
            "message": "",
        }

    @staticmethod
    def _safe_error_body(response: Any, limit: int = 500) -> str:
        if response is None:
            return ""
        try:
            return str(response.text)[:limit]
        except Exception:
            pass
        try:
            raw = response.read()
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")[:limit]
            return str(raw)[:limit]
        except Exception:
            return ""

    @staticmethod
    def _write_error_log(kind: str, message: str) -> None:
        try:
            root_dir = Path(__file__).resolve().parent.parent
            log_dir = root_dir / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "errors.log"
            payload = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "message": message,
            }
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResult:
        llm = self._llm_config()
        temperature = float(llm.get("temperature", 0.2))
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider (api_key/base_url) gefunden.")
        last_exc: Optional[Exception] = None
        for idx, provider_id in enumerate(chain):
            provider_cfg, model, provider_type = self._provider_runtime(provider_id)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            retry_policy = self._retry_policy(channel="chat", provider_id=provider_id)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            def call_provider() -> str:
                tmo = self._timeout
                if provider_type in {"openai_compatible", "xai"}:
                    return self._chat_openai_compatible_msgs(base_url, api_key, model, messages, temperature, timeout=tmo)
                if provider_type == "gemini":
                    return self._chat_gemini_msgs(base_url, api_key, model, messages, temperature, timeout=tmo)
                if provider_type == "anthropic":
                    return self._chat_anthropic_msgs(base_url, api_key, model, messages, temperature, timeout=tmo)
                raise LLMRouterError(f"Unbekannter provider type: {provider_type}")

            try:
                text = self._with_retry(call_provider, retry_policy, channel="chat", provider_id=provider_id, model=model)
                if idx > 0:
                    self._write_error_log(
                        "llm_failover_used",
                        f"selected_provider={provider_id} model={model}",
                    )
                return LLMResult(
                    ok=True,
                    provider=provider_id,
                    model=model,
                    text=text,
                    message="Antwort erfolgreich erzeugt.",
                )
            except httpx.HTTPStatusError as exc:
                body = self._safe_error_body(exc.response, limit=500) or str(exc)
                status = exc.response.status_code if exc.response is not None else "?"
                self._write_error_log(
                    "llm_http_status",
                    f"status={status} provider={provider_id} model={model} body={body}",
                )
                last_exc = exc
            except (httpx.HTTPError, LLMRouterError) as exc:
                self._write_error_log(
                    "llm_provider_error",
                    f"provider={provider_id} model={model} error={exc}",
                )
                last_exc = exc
        if last_exc:
            raise LLMRouterError(f"Alle Provider fehlgeschlagen: {last_exc}") from last_exc
        raise LLMRouterError("Alle Provider fehlgeschlagen.")

    def chat_messages(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> LLMResult:
        llm = self._llm_config()
        temp = float(llm.get("temperature", 0.2)) if temperature is None else float(temperature)
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider (api_key/base_url) gefunden.")
        last_exc: Optional[Exception] = None
        for idx, provider_id in enumerate(chain):
            provider_cfg, model, provider_type = self._provider_runtime(provider_id)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            retry_policy = self._retry_policy(channel="chat", provider_id=provider_id)

            def call_provider() -> str:
                tmo = self._timeout
                if provider_type in {"openai_compatible", "xai"}:
                    return self._chat_openai_compatible_msgs(base_url, api_key, model, messages, temp, timeout=tmo)
                if provider_type == "gemini":
                    return self._chat_gemini_msgs(base_url, api_key, model, messages, temp, timeout=tmo)
                if provider_type == "anthropic":
                    return self._chat_anthropic_msgs(base_url, api_key, model, messages, temp, timeout=tmo)
                raise LLMRouterError(f"Unbekannter provider type: {provider_type}")

            try:
                text = self._with_retry(call_provider, retry_policy, channel="chat", provider_id=provider_id, model=model)
                return LLMResult(ok=True, provider=provider_id, model=model, text=text, message="OK")
            except Exception as exc:
                last_exc = exc
                continue
        raise LLMRouterError(f"Alle Provider fehlgeschlagen: {last_exc}")

    @staticmethod
    def _chat_openai_compatible_msgs(base_url: str, api_key: str, model: str, messages: List[Dict[str, str]], temperature: float, timeout: int = 120) -> str:
        url = f"{base_url}/chat/completions"
        payload = {"model": model, "messages": messages, "temperature": temperature}
        headers = {"Content-Type": "application/json"}
        key = str(api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = str(msg.get("content", "") or "").strip()
        reasoning = str(msg.get("reasoning_content", "") or "").strip()
        
        if reasoning:
            return f"<think>\n{reasoning}\n</think>\n\n{content}".strip()
        return content or "(leere Antwort)"

    @staticmethod
    def _chat_gemini_msgs(base_url: str, api_key: str, model: str, messages: List[Dict[str, str]], temperature: float, timeout: int = 120) -> str:
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        params = {"key": api_key}
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates: return "(keine Antwort)"
        parts = candidates[0].get("content", {}).get("parts", [])
        out = []
        for p in parts:
            if "text" in p:
                out.append(str(p["text"]))
        return "\n".join(out).strip()

    def _chat_anthropic_msgs(self, base_url: str, api_key: str, model: str, messages: List[Dict[str, str]], temperature: float, timeout: int = 120) -> str:
        """Anthropic Messages API mit automatischem Prompt Caching Support."""
        url = f"{base_url}/v1/messages"
        
        # Prüfe ob Caching aktiviert werden soll
        use_caching = self._should_use_prompt_caching(model)
        
        # System Messages extrahieren und ggf. mit Cache-Control versehen
        system_content = []
        msgs = []
        
        for m in messages:
            if m["role"] == "system":
                content = m["content"]
                if use_caching and isinstance(content, str):
                    # Prüfe ob groß genug für Caching (>1024 Tokens ≈ >4096 chars)
                    if len(content) >= 4096:
                        # Als Cache-Block markieren
                        system_content.append({
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"}
                        })
                    else:
                        # Zu klein, normal hinzufügen
                        system_content.append({"type": "text", "text": content})
                elif isinstance(content, str):
                    system_content.append({"type": "text", "text": content})
                else:
                    # Content ist bereits strukturiert
                    system_content.append(content)
            else:
                msgs.append(m)
        
        # Payload bauen
        payload = {"model": model, "max_tokens": 4096, "temperature": temperature, "messages": msgs}
        
        # System Content hinzufügen (entweder als String oder als strukturierte Blöcke)
        if system_content:
            if len(system_content) == 1 and isinstance(system_content[0], dict) and system_content[0].get("type") == "text" and "cache_control" not in system_content[0]:
                # Einfacher String ohne Caching
                payload["system"] = system_content[0]["text"]
            else:
                # Strukturierte Blöcke (mit oder ohne Caching)
                payload["system"] = system_content
        
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        
        # Cache-Stats loggen (falls vorhanden)
        if use_caching and "usage" in data:
            self._log_cache_stats(data.get("usage", {}))
        
        # Text extrahieren
        out = []
        for item in data.get("content", []):
            if item.get("type") == "text":
                out.append(str(item.get("text", "")))
        
        return "\n".join(out).strip()

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def chat_json(self, prompt: str, schema_name: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        llm = self._llm_config()
        temperature = float(llm.get("temperature", 0.2))
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider (api_key/base_url) gefunden.")
        last_exc: Optional[Exception] = None
        for idx, provider_id in enumerate(chain):
            provider_cfg, model, provider_type = self._provider_runtime(provider_id)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            retry_policy = self._retry_policy(channel="json", provider_id=provider_id)

            def call_provider() -> Dict[str, Any]:
                tmo = self._timeout
                if provider_type == "gemini":
                    return self._chat_json_gemini(base_url, api_key, model, prompt, temperature, schema, timeout=tmo)
                if provider_type in {"openai_compatible", "xai"}:
                    return self._chat_json_openai_compatible(base_url, api_key, model, prompt, temperature, schema_name, schema, timeout=tmo)
                if provider_type == "anthropic":
                    text = self._chat_anthropic(base_url, api_key, model, prompt, temperature, timeout=tmo)
                    obj = self._extract_json_object(text)
                    if obj is None:
                        raise LLMRouterError("Anthropic JSON-Parsing fehlgeschlagen.")
                    return obj
                raise LLMRouterError(f"Unbekannter provider type: {provider_type}")

            try:
                obj = self._with_retry(call_provider, retry_policy, channel="json", provider_id=provider_id, model=model)
                if idx > 0:
                    self._write_error_log(
                        "llm_json_failover_used",
                        f"selected_provider={provider_id} model={model}",
                    )
                return obj
            except httpx.HTTPStatusError as exc:
                body = self._safe_error_body(exc.response, limit=500) or str(exc)
                status = exc.response.status_code if exc.response is not None else "?"
                self._write_error_log(
                    "llm_json_http_status",
                    f"status={status} provider={provider_id} model={model} body={body}",
                )
                last_exc = exc
            except (httpx.HTTPError, LLMRouterError) as exc:
                self._write_error_log(
                    "llm_json_provider_error",
                    f"provider={provider_id} model={model} error={exc}",
                )
                last_exc = exc
        if last_exc:
            raise LLMRouterError(f"Alle Provider fuer JSON fehlgeschlagen: {last_exc}") from last_exc
        raise LLMRouterError("Alle Provider fuer JSON fehlgeschlagen.")

    def chat_tool_calls(
        self,
        *,
        prompt: str,
        tools: List[Dict[str, Any]],
        provider_id: str = "",
        model: str = "",
        temperature: Optional[float] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        llm = self._llm_config()
        temp = float(llm.get("temperature", 0.2)) if temperature is None else float(temperature)
        chain = [str(provider_id).strip()] if str(provider_id).strip() else self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider (api_key/base_url) gefunden.")
        last_exc: Optional[Exception] = None
        for idx, pid in enumerate(chain):
            provider_cfg, model_runtime, provider_type = self._provider_runtime(pid)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            retry_policy = self._retry_policy(channel="json", provider_id=pid)
            model_use = str(model or model_runtime).strip() or model_runtime

            def call_provider() -> List[Dict[str, Any]]:
                tmo = self._timeout
                if provider_type in {"openai_compatible", "xai"}:
                    return self._chat_tools_openai_compatible(
                        base_url=base_url,
                        api_key=api_key,
                        model=model_use,
                        prompt=prompt,
                        temperature=temp,
                        tools=tools,
                        profile=profile or {},
                        timeout=tmo
                    )
                if provider_type == "gemini":
                    return self._chat_tools_gemini(
                        base_url=base_url,
                        api_key=api_key,
                        model=model_use,
                        prompt=prompt,
                        temperature=temp,
                        tools=tools,
                        profile=profile or {},
                        timeout=tmo
                    )
                if provider_type == "anthropic":
                    return self._chat_tools_anthropic(
                        base_url=base_url,
                        api_key=api_key,
                        model=model_use,
                        prompt=prompt,
                        temperature=temp,
                        tools=tools,
                        profile=profile or {},
                        timeout=tmo
                    )
                raise LLMRouterError(f"Unbekannter provider type: {provider_type}")

            try:
                out = self._with_retry(call_provider, retry_policy, channel="json", provider_id=pid, model=model_use)
                if idx > 0:
                    self._write_error_log(
                        "llm_tools_failover_used",
                        f"selected_provider={pid} model={model_use}",
                    )
                return out
            except httpx.HTTPStatusError as exc:
                body = self._safe_error_body(exc.response, limit=500) or str(exc)
                status = exc.response.status_code if exc.response is not None else "?"
                self._write_error_log(
                    "llm_tools_http_status",
                    f"status={status} provider={pid} model={model_use} body={body}",
                )
                last_exc = exc
            except (httpx.HTTPError, LLMRouterError) as exc:
                self._write_error_log(
                    "llm_tools_provider_error",
                    f"provider={pid} model={model_use} error={exc}",
                )
                last_exc = exc
        if last_exc:
            raise LLMRouterError(f"Alle Provider fuer Tools fehlgeschlagen: {last_exc}") from last_exc
        raise LLMRouterError("Alle Provider fuer Tools fehlgeschlagen.")

    def chat_messages_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: Optional[float] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """
        Multi-turn nativer Tool-Calling-Aufruf.

        Nimmt eine vollständige Message-History (system/user/assistant/tool)
        und gibt zurück:
          text        – Freitext-Antwort (leer wenn Tool-Calls vorhanden)
          tool_calls  – Liste von {"kind": name, "_tool_id": id, **args}
          stop_reason – "tool_use" | "end_turn" | "stop" | "error"
        """
        llm = self._llm_config()
        temp = float(llm.get("temperature", 0.2)) if temperature is None else float(temperature)
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider gefunden.")
        last_exc: Optional[Exception] = None
        for pid in chain:
            provider_cfg, model_runtime, provider_type = self._provider_runtime(pid)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            tmo = self._timeout
            try:
                if provider_type == "anthropic":
                    return self._msgs_with_tools_anthropic(
                        base_url=base_url, api_key=api_key, model=model_runtime,
                        messages=messages, tools=tools, temperature=temp, timeout=tmo,
                    )
                if provider_type in {"openai_compatible", "xai"}:
                    return self._msgs_with_tools_openai(
                        base_url=base_url, api_key=api_key, model=model_runtime,
                        messages=messages, tools=tools, temperature=temp, timeout=tmo,
                    )
                if provider_type == "gemini":
                    return self._msgs_with_tools_gemini(
                        base_url=base_url, api_key=api_key, model=model_runtime,
                        messages=messages, tools=tools, temperature=temp, timeout=tmo,
                    )
            except Exception as exc:
                self._write_error_log("msgs_with_tools_error", f"provider={pid} error={exc}")
                last_exc = exc
        raise LLMRouterError(f"chat_messages_with_tools fehlgeschlagen: {last_exc}")

    @staticmethod
    def _history_to_anthropic(
        messages: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Konvertiert neutrale K.AI-History → Anthropic API Format.
        Gibt (system_text, messages_list) zurück.
        System-Nachrichten werden zusammengeführt, tool-Ergebnisse als
        user-Nachricht mit tool_result-Block eingefügt.
        """
        system_parts: List[str] = []
        out: List[Dict[str, Any]] = []

        for msg in messages:
            role = str(msg.get("role", "")).strip()
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(str(content))
                continue

            if role == "user":
                imgs = msg.get("_images") or []
                if imgs:
                    blocks: List[Dict[str, Any]] = [{"type": "text", "text": str(content)}]
                    for img in imgs:
                        blocks.append({"type": "image", "source": {
                            "type": "base64",
                            "media_type": str(img.get("media_type", "image/jpeg")),
                            "data": str(img.get("data", "")),
                        }})
                    out.append({"role": "user", "content": blocks})
                else:
                    out.append({"role": "user", "content": str(content)})
                continue

            if role == "assistant":
                # Enthält der assistant-Turn Tool-Calls?
                tc_list = msg.get("_tool_calls", [])
                if tc_list and isinstance(tc_list, list):
                    blocks: List[Dict[str, Any]] = []
                    if content:
                        blocks.append({"type": "text", "text": str(content)})
                    for tc in tc_list:
                        blocks.append({
                            "type": "tool_use",
                            "id": str(tc.get("_tool_id", "") or ""),
                            "name": str(tc.get("kind", "") or ""),
                            "input": {k: v for k, v in tc.items() if k not in ("kind", "_tool_id")},
                        })
                    out.append({"role": "assistant", "content": blocks})
                else:
                    out.append({"role": "assistant", "content": str(content)})
                continue

            if role == "tool":
                tool_id = str(msg.get("_tool_id", "") or "")
                result = str(content)
                # Tool-Ergebnisse müssen als user-Nachricht mit tool_result-Block kommen
                # Mehrere aufeinanderfolgende tool-Ergebnisse werden zusammengefasst
                if out and out[-1]["role"] == "user" and isinstance(out[-1].get("content"), list):
                    out[-1]["content"].append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    })
                else:
                    out.append({"role": "user", "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    }]})
                continue

        return "\n\n".join(system_parts), out

    @staticmethod
    def _history_to_openai(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Konvertiert neutrale K.AI-History → OpenAI-kompatibles Format.
        tool-Ergebnisse werden als role="tool" mit tool_call_id eingefügt.
        """
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip()
            content = msg.get("content", "")

            if role == "system":
                out.append({"role": "system", "content": str(content)})
                continue

            if role == "user":
                imgs = msg.get("_images") or []
                if imgs:
                    blocks: List[Dict[str, Any]] = [{"type": "text", "text": str(content)}]
                    for img in imgs:
                        url = f"data:{img.get('media_type', 'image/jpeg')};base64,{img.get('data', '')}"
                        blocks.append({"type": "image_url", "image_url": {"url": url}})
                    out.append({"role": "user", "content": blocks})
                else:
                    out.append({"role": "user", "content": str(content)})
                continue

            if role == "assistant":
                tc_list = msg.get("_tool_calls", [])
                if tc_list and isinstance(tc_list, list):
                    oai_calls = []
                    for tc in tc_list:
                        tc_id = str(tc.get("_tool_id", "") or "")
                        name = str(tc.get("kind", "") or "")
                        args = {k: v for k, v in tc.items() if k not in ("kind", "_tool_id")}
                        oai_calls.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                        })
                    out.append({"role": "assistant", "content": str(content) or None, "tool_calls": oai_calls})
                else:
                    out.append({"role": "assistant", "content": str(content)})
                continue

            if role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": str(msg.get("_tool_id", "") or ""),
                    "content": str(content),
                })
                continue

        return out

    def _msgs_with_tools_anthropic(
        self, *, base_url: str, api_key: str, model: str,
        messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
        temperature: float, timeout: int,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        system_text, converted = LLMRouter._history_to_anthropic(messages)
        a_tools = []
        for t in tools:
            fn = t.get("function", {}) if isinstance(t.get("function"), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            if not name:
                continue
            a_tools.append({
                "name": name,
                "description": str(fn.get("description", "") or ""),
                "input_schema": fn.get("parameters", {}),
            })
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": converted,
        }
        # Prompt Caching: System-Prompt als strukturierter Block mit cache_control
        # (identische Logik wie _chat_anthropic_msgs — cacht nur wenn Claude 3+ und >=4096 chars)
        use_caching = self._should_use_prompt_caching(model)
        if system_text:
            if use_caching and len(system_text) >= 4096:
                payload["system"] = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]
            else:
                payload["system"] = system_text
        if a_tools:
            payload["tools"] = a_tools
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(f"{base_url}/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # Cache-Stats loggen (falls aktiviert)
        if use_caching and isinstance(data, dict) and "usage" in data:
            self._log_cache_stats(data["usage"])
        stop_reason = str(data.get("stop_reason", "end_turn") or "end_turn")
        blocks = data.get("content", []) if isinstance(data, dict) else []
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            btype = str(b.get("type", "")).strip()
            if btype == "text":
                text_parts.append(str(b.get("text", "")))
            elif btype == "tool_use":
                name = str(b.get("name", "") or "").strip()
                inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                tool_id = str(b.get("id", "") or "")
                if name:
                    tool_calls.append({"kind": name, "_tool_id": tool_id, **inp})
        return "\n".join(text_parts).strip(), tool_calls, stop_reason

    @staticmethod
    def _msgs_with_tools_openai(
        *, base_url: str, api_key: str, model: str,
        messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
        temperature: float, timeout: int,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        converted = LLMRouter._history_to_openai(messages)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = data.get("choices", [{}])[0] if isinstance(data, dict) else {}
        stop_reason = str(choice.get("finish_reason", "stop") or "stop")
        msg = choice.get("message", {}) if isinstance(choice, dict) else {}
        text = str(msg.get("content", "") or "").strip()
        raw_calls = msg.get("tool_calls", []) if isinstance(msg.get("tool_calls"), list) else []
        tool_calls: List[Dict[str, Any]] = []
        for c in raw_calls:
            if not isinstance(c, dict):
                continue
            fn = c.get("function", {}) if isinstance(c.get("function"), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            tool_id = str(c.get("id", "") or "")
            raw_args = str(fn.get("arguments", "") or "")
            args: Dict[str, Any] = {}
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                pass
            if name:
                tool_calls.append({"kind": name, "_tool_id": tool_id, **args})
        return text, tool_calls, stop_reason

    @staticmethod
    def _msgs_with_tools_gemini(
        *, base_url: str, api_key: str, model: str,
        messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
        temperature: float, timeout: int,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        # Gemini nutzt contents-Format, system wird als erster user-Turn eingefügt
        contents: List[Dict[str, Any]] = []
        system_text = ""
        for msg in messages:
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", ""))
            if role == "system":
                system_text += content + "\n"
                continue
            if role == "user":
                parts: List[Dict[str, Any]] = [{"text": content}]
                for img in (msg.get("_images") or []):
                    parts.append({"inline_data": {
                        "mime_type": str(img.get("media_type", "image/jpeg")),
                        "data": str(img.get("data", "")),
                    }})
                contents.append({"role": "user", "parts": parts})
            elif role == "assistant":
                tc_list = msg.get("_tool_calls", [])
                if tc_list:
                    parts = []
                    if content:
                        parts.append({"text": content})
                    for tc in tc_list:
                        name = str(tc.get("kind", "") or "")
                        args = {k: v for k, v in tc.items() if k not in ("kind", "_tool_id")}
                        parts.append({"functionCall": {"name": name, "args": args}})
                    contents.append({"role": "model", "parts": parts})
                else:
                    contents.append({"role": "model", "parts": [{"text": content}]})
            elif role == "tool":
                tool_name = str(msg.get("tool", "") or "")
                result = content
                contents.append({"role": "user", "parts": [{"functionResponse": {
                    "name": tool_name, "response": {"result": result}
                }}]})
        # System-Text als erster User-Turn prependen
        if system_text and contents:
            first = contents[0]
            if first["role"] == "user":
                first["parts"] = [{"text": system_text.strip()}] + first["parts"]
        elif system_text:
            contents.insert(0, {"role": "user", "parts": [{"text": system_text.strip()}]})

        declarations = []
        for t in tools:
            fn = t.get("function", {}) if isinstance(t.get("function"), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            if not name:
                continue
            pars = LLMRouter._sanitize_schema_for_gemini(
                fn.get("parameters", {}), strip_additional=True
            )
            declarations.append({"name": name, "description": str(fn.get("description", "") or ""), "parameters": pars})

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        url = f"{base_url}/v1beta/models/{model}:generateContent"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, params={"key": api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        stop_reason = "end_turn"
        if candidates and isinstance(candidates[0], dict):
            stop_reason = str(candidates[0].get("finishReason", "STOP") or "STOP").lower()
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            if "text" in p:
                text_parts.append(str(p["text"]))
            fc = p.get("functionCall", {}) if isinstance(p.get("functionCall"), dict) else {}
            name = str(fc.get("name", "") or "").strip()
            if name:
                args = fc.get("args", {}) if isinstance(fc.get("args"), dict) else {}
                tool_calls.append({"kind": name, "_tool_id": "", **args})
        return "\n".join(text_parts).strip(), tool_calls, stop_reason

    def stream_chat(self, prompt: str) -> Iterator[str]:
        llm = self._llm_config()
        temperature = float(llm.get("temperature", 0.2))
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider (api_key/base_url) gefunden.")
        last_exc: Optional[Exception] = None
        for provider_id in chain:
            provider_cfg, model, provider_type = self._provider_runtime(provider_id)
            api_key = str(provider_cfg.get("api_key", "")).strip()
            base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
            retry_policy = self._retry_policy(channel="stream", provider_id=provider_id)
            max_attempts = int(retry_policy.get("max_attempts", 1))
            attempt = 1
            while attempt <= max_attempts:
                yielded_any = False
                tmo = self._timeout
                try:
                    if provider_type == "gemini":
                        iterator = self._stream_gemini(base_url, api_key, model, prompt, temperature, timeout=tmo)
                    elif provider_type in {"openai_compatible", "xai"}:
                        iterator = self._stream_openai_compatible(base_url, api_key, model, prompt, temperature, timeout=tmo)
                    elif provider_type == "anthropic":
                        iterator = self._stream_anthropic(base_url, api_key, model, prompt, temperature, timeout=tmo)
                    else:
                        raise LLMRouterError(f"Unbekannter provider type: {provider_type}")
                    for chunk in iterator:
                        yielded_any = True
                        yield chunk
                    return
                except httpx.HTTPStatusError as exc:
                    body = self._safe_error_body(exc.response, limit=500) or str(exc)
                    status = exc.response.status_code if exc.response is not None else 0
                    self._write_error_log(
                        "llm_stream_http_status",
                        f"status={status} provider={provider_id} model={model} body={body}",
                    )
                    last_exc = exc
                    if yielded_any:
                        raise LLMRouterError(f"Stream abgebrochen nach Teilantwort: {body}") from exc
                    if not self._is_retryable_status(status, retry_policy) or attempt >= max_attempts:
                        break
                    self._sleep_for_retry(
                        attempt=attempt,
                        retry_policy=retry_policy,
                        retry_after=self._parse_retry_after(exc.response.headers.get("retry-after") if exc.response is not None else None),
                        channel="stream",
                        provider_id=provider_id,
                        model=model,
                        reason=f"http_{status}",
                    )
                    attempt += 1
                except (httpx.HTTPError, LLMRouterError) as exc:
                    self._write_error_log(
                        "llm_stream_provider_error",
                        f"provider={provider_id} model={model} error={exc}",
                    )
                    last_exc = exc
                    if yielded_any:
                        raise
                    if (not bool(retry_policy.get("retry_on_network_errors", True))) or attempt >= max_attempts:
                        break
                    self._sleep_for_retry(
                        attempt=attempt,
                        retry_policy=retry_policy,
                        retry_after=None,
                        channel="stream",
                        provider_id=provider_id,
                        model=model,
                        reason="network_error",
                    )
                    attempt += 1
            continue

        # final fallback: non-stream answer chunked
        result = self.chat(prompt)
        for i in range(0, len(result.text), 18):
            yield result.text[i : i + 18]
            time.sleep(0.02)

    def stream_chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_text_chunk: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """
        Streaming-Version von chat_messages_with_tools.
        Ruft on_text_chunk(chunk) live für jeden Text-Token auf.
        Gibt (full_text, tool_calls, stop_reason) zurück — identisch zu chat_messages_with_tools.
        Bei Providern ohne Streaming-Support oder bei Fehler: transparenter Fallback auf blocking.
        """
        chain = self._provider_chain()
        if not chain:
            raise LLMRouterError("Kein verwendbarer Provider gefunden.")
        provider_id = chain[0]
        _, _, provider_type = self._provider_runtime(provider_id)
        if provider_type not in {"openai_compatible", "xai"}:
            # Anthropic streaming + tool calls ist komplex → blocking Fallback
            return self.chat_messages_with_tools(messages, tools)
        try:
            return self._stream_with_tools_openai(messages, tools, on_text_chunk, provider_id)
        except Exception:
            # Fehler im Stream → blocking Fallback, keine Regression
            return self.chat_messages_with_tools(messages, tools)

    def _stream_with_tools_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_text_chunk: Optional[Callable[[str], None]],
        provider_id: str,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """Streamt Text-Tokens live, akkumuliert Tool-Call-Deltas für OpenAI-compatible APIs."""
        provider_cfg, model, _ = self._provider_runtime(provider_id)
        api_key = str(provider_cfg.get("api_key", "")).strip()
        base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
        temp = float(self._llm_config().get("temperature", 0.2))

        converted = LLMRouter._history_to_openai(messages)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temp,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        full_text = ""
        tool_calls_raw: Dict[int, Dict[str, str]] = {}
        stop_reason = "stop"

        with httpx.Client(timeout=self._timeout, trust_env=False) as client:
            with client.stream("POST", f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        finish = choice.get("finish_reason")
                        if finish:
                            stop_reason = finish
                        # Text-Token live weiterleiten
                        content = delta.get("content") or ""
                        if content:
                            full_text += content
                            if on_text_chunk:
                                try:
                                    on_text_chunk(content)
                                except Exception:
                                    pass
                        # Tool-Call-Deltas akkumulieren
                        for tc_delta in delta.get("tool_calls", []):
                            idx = int(tc_delta.get("index", 0))
                            if idx not in tool_calls_raw:
                                tool_calls_raw[idx] = {"id": "", "name": "", "arguments": ""}
                            if "id" in tc_delta:
                                tool_calls_raw[idx]["id"] = str(tc_delta["id"])
                            fn = tc_delta.get("function", {})
                            if "name" in fn:
                                tool_calls_raw[idx]["name"] += str(fn["name"])
                            if "arguments" in fn:
                                tool_calls_raw[idx]["arguments"] += str(fn["arguments"])

        # Tool-Calls parsen
        parsed_tool_calls: List[Dict[str, Any]] = []
        for idx in sorted(tool_calls_raw.keys()):
            tc = tool_calls_raw[idx]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except Exception:
                args = {}
            if isinstance(args, dict):
                parsed_tool_calls.append({"kind": tc["name"], "_tool_id": tc["id"], **args})

        return full_text, parsed_tool_calls, stop_reason

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[float]:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            return float(raw)
        try:
            dt = parsedate_to_datetime(raw)
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - now).total_seconds())
        except Exception:
            return None

    @staticmethod
    def _is_retryable_status(status: int, retry_policy: Dict[str, Any]) -> bool:
        status_set = retry_policy.get("retry_on_status", set())
        if isinstance(status_set, set):
            return status in status_set
        return status in {429, 500, 502, 503, 504}

    def _sleep_for_retry(
        self,
        attempt: int,
        retry_policy: Dict[str, Any],
        retry_after: Optional[float],
        channel: str,
        provider_id: str,
        model: str,
        reason: str,
    ) -> None:
        base = float(retry_policy.get("base_delay_seconds", 1.0))
        factor = float(retry_policy.get("backoff_factor", 2.0))
        cap = float(retry_policy.get("max_delay_seconds", 8.0))
        jitter_ratio = float(retry_policy.get("jitter_ratio", 0.2))
        computed = base * (factor ** max(0, attempt - 1))
        delay = min(cap, computed)
        if retry_after is not None:
            delay = min(cap, max(0.0, float(retry_after)))
        if delay > 0 and jitter_ratio > 0:
            spread = delay * jitter_ratio
            delay = max(0.0, min(cap, delay + random.uniform(-spread, spread)))
        self._write_error_log(
            "llm_retry",
            (
                f"channel={channel} provider={provider_id} model={model} "
                f"attempt={attempt} reason={reason} sleep={delay:.2f}s"
            ),
        )
        # Nutzer via Callback benachrichtigen (Telegram / Discord / WebUI)
        if delay > 0:
            _fire_retry_notify(reason=reason, delay_sec=delay, provider=provider_id, model=model)
        if delay > 0:
            time.sleep(delay)

    def _with_retry(
        self,
        fn,
        retry_policy: Dict[str, Any],
        channel: str,
        provider_id: str,
        model: str,
    ):
        attempt = 1
        max_attempts = int(retry_policy.get("max_attempts", 1))
        while True:
            try:
                # lightweight call tracing for diagnostics
                try:
                    # Try to read current trace_id from runtime (main._current_trace_id)
                    trace_id = None
                    try:
                        from app.main import _current_trace_id
                        trace_id = str(_current_trace_id() or "").strip() or None
                    except Exception:
                        trace_id = None
                    root_dir = Path(__file__).resolve().parent.parent
                    calls_dir = root_dir / "data" / "logs"
                    calls_dir.mkdir(parents=True, exist_ok=True)
                    calls_path = calls_dir / "llm_calls.log"
                    payload = {"ts": datetime.now(timezone.utc).isoformat(), "provider": provider_id, "model": model, "channel": channel, "attempt": attempt, "event": "call_start"}
                    if trace_id:
                        payload["trace_id"] = trace_id
                    with calls_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                res = fn()
                try:
                    try:
                        from app.main import _current_trace_id
                        trace_id = str(_current_trace_id() or "").strip() or None
                    except Exception:
                        trace_id = None
                    with (Path(__file__).resolve().parent.parent / "data" / "logs" / "llm_calls.log").open("a", encoding="utf-8") as fh:
                        payload = {"ts": datetime.now(timezone.utc).isoformat(), "provider": provider_id, "model": model, "channel": channel, "attempt": attempt, "event": "call_success"}
                        if trace_id:
                            payload["trace_id"] = trace_id
                        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return res
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                try:
                    try:
                        from app.main import _current_trace_id
                        trace_id = str(_current_trace_id() or "").strip() or None
                    except Exception:
                        trace_id = None
                    with (Path(__file__).resolve().parent.parent / "data" / "logs" / "llm_calls.log").open("a", encoding="utf-8") as fh:
                        payload = {"ts": datetime.now(timezone.utc).isoformat(), "provider": provider_id, "model": model, "channel": channel, "attempt": attempt, "event": "http_status", "status": status}
                        if trace_id:
                            payload["trace_id"] = trace_id
                        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                if (not self._is_retryable_status(status, retry_policy)) or attempt >= max_attempts:
                    raise
                self._sleep_for_retry(
                    attempt=attempt,
                    retry_policy=retry_policy,
                    retry_after=self._parse_retry_after(exc.response.headers.get("retry-after") if exc.response is not None else None),
                    channel=channel,
                    provider_id=provider_id,
                    model=model,
                    reason=f"http_{status}",
                )
                attempt += 1
            except httpx.HTTPError:
                try:
                    try:
                        from app.main import _current_trace_id
                        trace_id = str(_current_trace_id() or "").strip() or None
                    except Exception:
                        trace_id = None
                    with (Path(__file__).resolve().parent.parent / "data" / "logs" / "llm_calls.log").open("a", encoding="utf-8") as fh:
                        payload = {"ts": datetime.now(timezone.utc).isoformat(), "provider": provider_id, "model": model, "channel": channel, "attempt": attempt, "event": "network_error"}
                        if trace_id:
                            payload["trace_id"] = trace_id
                        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                if (not bool(retry_policy.get("retry_on_network_errors", True))) or attempt >= max_attempts:
                    raise
                self._sleep_for_retry(
                    attempt=attempt,
                    retry_policy=retry_policy,
                    retry_after=None,
                    channel=channel,
                    provider_id=provider_id,
                    model=model,
                    reason="network_error",
                )
                attempt += 1

    @staticmethod
    def _chat_openai_compatible(
        base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120
    ) -> str:
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        headers = {"Content-Type": "application/json"}
        key = str(api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            or "(leere Antwort)"
        )

    @classmethod
    def _chat_json_openai_compatible(
        cls,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        schema_name: str,
        schema: Dict[str, Any],
        timeout: int = 120,
    ) -> Dict[str, Any]:
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = str(api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                # Compatibility fallback for providers that do not support json_schema.
                fallback_payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                }
                resp = client.post(url, headers=headers, json=fallback_payload)
            resp.raise_for_status()
            data = resp.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        obj = cls._extract_json_object(text)
        if obj is None:
            raise LLMRouterError("OpenAI-compatible JSON-Parsing fehlgeschlagen.")
        return obj

    @staticmethod
    def _chat_gemini(base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120) -> str:
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        params = {"key": api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return "(keine Antwort)"
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if part.get("text")]
        return "\n".join(text_parts).strip() or "(leere Antwort)"

    @staticmethod
    def _sanitize_schema_for_gemini(value: Any, strip_additional: bool = True) -> Any:
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            source_dict = dict(value)

            # Gemini-spezifische Mappings für anyOf/oneOf
            if "anyOf" in source_dict and "any_of" not in source_dict:
                source_dict["any_of"] = source_dict.pop("anyOf")
            elif "oneOf" in source_dict and "one_of" not in source_dict:
                source_dict["one_of"] = source_dict.pop("oneOf")

            for kk, vv in source_dict.items():
                if strip_additional and str(kk) == "additionalProperties":
                    continue
                if str(kk) == "type" and isinstance(vv, str):
                    out[str(kk)] = vv.upper()
                    continue

                # Radikale Bereinigung für Gemini: any_of/one_of/all_of oft problematisch in tool-schemas
                if str(kk) in {"any_of", "one_of", "all_of"} and isinstance(vv, list) and vv:
                    # Wir nehmen den ersten Zweig als Repräsentanten, um Schema-Fehler zu vermeiden
                    first_branch = vv[0]
                    if isinstance(first_branch, dict):
                        # Merging von required-Feldern aus dem Zweig in das Haupt-Objekt
                        if "required" in first_branch and isinstance(first_branch["required"], list):
                            existing_req = out.get("required", [])
                            if not isinstance(existing_req, list): existing_req = []
                            out["required"] = list(dict.fromkeys(existing_req + first_branch["required"]))
                        
                        # Merging von properties falls vorhanden
                        if "properties" in first_branch and isinstance(first_branch["properties"], dict):
                            existing_props = out.get("properties", {})
                            if not isinstance(existing_props, dict): existing_props = {}
                            existing_props.update(first_branch["properties"])
                            out["properties"] = existing_props
                    continue

                out[str(kk)] = LLMRouter._sanitize_schema_for_gemini(vv, strip_additional)

            # Letzter Check: Required-Felder müssen in Properties existieren
            if "required" in out and isinstance(out["required"], list) and "properties" in out:
                props = out.get("properties", {})
                out["required"] = [r for r in out["required"] if r in props]

            return out
        if isinstance(value, list):
            return [LLMRouter._sanitize_schema_for_gemini(x, strip_additional) for x in value]
        return value

    @classmethod
    def _chat_json_gemini(
        cls,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        schema: Dict[str, Any],
        timeout: int = 120,
    ) -> Dict[str, Any]:
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        params = {"key": api_key}

        sanitized_schema = cls._sanitize_schema_for_gemini(schema)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": sanitized_schema,
            },
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, params=params, json=payload)
            if resp.status_code >= 400:
                fallback_payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature},
                }
                resp = client.post(url, params=params, json=fallback_payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMRouterError("Gemini JSON-Antwort fehlt.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if part.get("text")]
        text = "\n".join(text_parts).strip()
        obj = cls._extract_json_object(text)
        if obj is None:
            raise LLMRouterError("Gemini JSON-Parsing fehlgeschlagen.")
        return obj

    @staticmethod
    def _chat_tools_openai_compatible(
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        tools: List[Dict[str, Any]],
        profile: Dict[str, Any],
        timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            
        headers = {"Content-Type": "application/json"}
        key = str(api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        msg = data.get("choices", [{}])[0].get("message", {}) if isinstance(data, dict) else {}
        calls = msg.get("tool_calls", []) if isinstance(msg.get("tool_calls", []), list) else []
        out: List[Dict[str, Any]] = []
        for c in calls:
            if not isinstance(c, dict):
                continue
            fn = c.get("function", {}) if isinstance(c.get("function", {}), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            raw_args = str(fn.get("arguments", "") or "").strip()
            if not name:
                continue
            args: Dict[str, Any] = {}
            if raw_args:
                try:
                    parsed = json.loads(raw_args)
                    if isinstance(parsed, dict):
                        args = parsed
                except Exception:
                    args = {}
            out.append({"kind": name, **args})
        return out

    @staticmethod
    def _chat_tools_gemini(
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        tools: List[Dict[str, Any]],
        profile: Dict[str, Any],
        timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        params = {"key": api_key}
        declarations: List[Dict[str, Any]] = []
        native_cfg = profile.get("native_tools", {}) if isinstance(profile.get("native_tools", {}), dict) else {}
        schema_cfg = native_cfg.get("schema", {}) if isinstance(native_cfg.get("schema", {}), dict) else {}
        strip_additional = bool(schema_cfg.get("strip_additional_properties", True)) # Default to True for Gemini

        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = t.get("function", {}) if isinstance(t.get("function", {}), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            desc = str(fn.get("description", "") or "").strip()
            pars = fn.get("parameters", {}) if isinstance(fn.get("parameters", {}), dict) else {}
            
            pars = LLMRouter._sanitize_schema_for_gemini(pars, strip_additional=strip_additional)
            
            if not name:
                continue
            declarations.append({"name": name, "description": desc, "parameters": pars})
            
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        if not candidates:
            return []
        parts = candidates[0].get("content", {}).get("parts", []) if isinstance(candidates[0], dict) else []
        out: List[Dict[str, Any]] = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            fc = p.get("functionCall", {}) if isinstance(p.get("functionCall", {}), dict) else {}
            name = str(fc.get("name", "") or "").strip()
            args = fc.get("args", {}) if isinstance(fc.get("args", {}), dict) else {}
            if not name:
                continue
            out.append({"kind": name, **args})
        return out

    @staticmethod
    def _chat_tools_anthropic(
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        tools: List[Dict[str, Any]],
        profile: Dict[str, Any],
        timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        url = f"{base_url}/v1/messages"
        a_tools: List[Dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = t.get("function", {}) if isinstance(t.get("function", {}), dict) else {}
            name = str(fn.get("name", "") or "").strip()
            desc = str(fn.get("description", "") or "").strip()
            schema = fn.get("parameters", {}) if isinstance(fn.get("parameters", {}), dict) else {}
            if not name:
                continue
            a_tools.append({"name": name, "description": desc, "input_schema": schema})
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if a_tools:
            payload["tools"] = a_tools
            
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        blocks = data.get("content", []) if isinstance(data, dict) else []
        out: List[Dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if str(b.get("type", "")).strip().lower() != "tool_use":
                continue
            name = str(b.get("name", "") or "").strip()
            inp = b.get("input", {}) if isinstance(b.get("input", {}), dict) else {}
            if not name:
                continue
            out.append({"kind": name, **inp})
        return out

    @staticmethod
    def _chat_anthropic(
        base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120
    ) -> str:
        url = f"{base_url}/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        chunks = data.get("content", [])
        text_parts = [str(item.get("text", "")) for item in chunks if item.get("type") == "text"]
        return "\n".join(text_parts).strip() or "(leere Antwort)"

    @staticmethod
    def _stream_openai_compatible(
        base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120
    ) -> Iterator[str]:
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        key = str(api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_line = line[6:].strip()
                    if data_line == "[DONE]":
                        break
                    payload_obj = json.loads(data_line)
                    chunk = (
                        payload_obj.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if chunk:
                        yield chunk

    @staticmethod
    def _stream_gemini(
        base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120
    ) -> Iterator[str]:
        url = f"{base_url}/v1beta/models/{model}:streamGenerateContent"
        params = {"key": api_key, "alt": "sse"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream("POST", url, params=params, json=payload) as resp:
                resp.raise_for_status()
                last_text = ""
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_line = line[6:].strip()
                    if not data_line:
                        continue
                    payload_obj = json.loads(data_line)
                    candidates = payload_obj.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = str(part.get("text", ""))
                        if not text:
                            continue
                        if text.startswith(last_text):
                            delta = text[len(last_text) :]
                        else:
                            delta = text
                        last_text = text
                        if delta:
                            yield delta

    @staticmethod
    def _stream_anthropic(
        base_url: str, api_key: str, model: str, prompt: str, temperature: float, timeout: int = 120
    ) -> Iterator[str]:
        url = f"{base_url}/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_line = line[6:].strip()
                    if not data_line:
                        continue
                    payload_obj = json.loads(data_line)
                    delta = payload_obj.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield str(delta["text"])
