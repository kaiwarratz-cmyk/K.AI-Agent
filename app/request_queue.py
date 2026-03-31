"""
Request Queue System für K.AI Agent
Verhindert Race Conditions bei parallelen Chat-Anfragen
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable


class ChatRequestQueue:
    """
    Queue für Chat-Anfragen, damit der Agent immer nur einen Task gleichzeitig bearbeitet.
    Verhindert Race Conditions bei Tool-Nutzung und Session-Updates.
    """
    
    def __init__(self):
        self.queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq_counter = 0          # tie-breaker for equal priorities
        self._seq_lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.pending_requests: Dict[str, tuple] = {}  # request_id -> queue item
        self.cancelled_requests: set = set()  # IDs von abgebrochenen Requests
        self.active_lock = threading.RLock()
        self.chat_reply_fn: Optional[Callable] = None
        
        # Watchdog Einstellungen
        self._watchdog_interval = 5
        self._overdue_timeout = 1800 # 30 Minuten für Agent-Tasks (ReAct-Loops)
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        
        # Queue warning threshold
        self._queue_warning_threshold: int = 20

    @staticmethod
    def _detect_priority(message: str) -> int:
        """Auto-detect priority from message text.
        0 = INTERRUPT, 1 = NEW_TASK/default, 2 = FOLLOWUP/simple
        """
        msg = message.strip().lower()
        interrupt_words = ["stop", "abbruch", "abbrechen", "cancel", "halt",
                           "nein lass", "vergiss", "vergessen", "neu anfangen"]
        if any(w in msg for w in interrupt_words):
            return 0
        simple_reactions = {"ok", "okay", "ja", "nein", "danke", "thx", "thanks",
                            "super", "gut", "cool", "weiter", "fertig", "done"}
        if len(msg) <= 15 and msg in simple_reactions:
            return 2
        return 1

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq_counter += 1
            return self._seq_counter

    def set_chat_reply_fn(self, fn: Callable):
        """Setzt die _chat_reply Funktion (wird von main.py aufgerufen)."""
        self.chat_reply_fn = fn

    def start(self, cfg: Optional[Dict[str, Any]] = None):
        """Startet den Worker-Thread.

        Fix 3: Optionaler cfg-Parameter liest max_step_timeout_sec aus der Config,
        damit der Watchdog den konfigurierten Wert statt des hardcodierten 1800s nutzt.
        """
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.chat_reply_fn:
            raise RuntimeError("chat_reply_fn muss gesetzt sein vor start()")

        if cfg and isinstance(cfg, dict):
            core = cfg.get("cli_core", {})
            step_t = int(core.get("max_step_timeout_sec", 1200) or 1200)
            self._overdue_timeout = max(step_t + 60, 300)  # Puffer +60 s

        self.stop_event.clear()
        try:
            from app.trace_utils import start_thread_with_trace
            self.worker_thread = start_thread_with_trace(self._process_queue, name="ChatRequestWorker", daemon=True)
        except Exception:
            self.worker_thread = threading.Thread(
                target=self._process_queue,
                daemon=True,
                name="ChatRequestWorker"
            )
            self.worker_thread.start()

        # Start watchdog thread
        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_stop.clear()
            try:
                from app.trace_utils import start_thread_with_trace
                self._watchdog_thread = start_thread_with_trace(self._watchdog_loop, name="ChatRequestWatchdog", daemon=True)
            except Exception:
                self._watchdog_thread = threading.Thread(
                    target=self._watchdog_loop,
                    daemon=True,
                    name="ChatRequestWatchdog"
                )
                self._watchdog_thread.start()

    def stop(self):
        """Stoppt den Worker-Thread gracefully."""
        self.stop_event.set()
        self._watchdog_stop.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=3)

    def submit(
        self,
        message: str,
        cfg: Dict[str, Any],
        result_callback: Callable[[Dict[str, Any]], None],
        **kwargs
    ) -> tuple[str, threading.Event]:
        """
        Fügt Request zur Queue hinzu. Priority wird auto-detektiert.
        
        Returns:
            (request_id, started_event)
        """
        priority = self._detect_priority(message)
        return self.submit_priority(message, priority, cfg, result_callback, **kwargs)

    def submit_priority(
        self,
        message: str,
        priority: int,
        cfg: Dict[str, Any],
        result_callback: Callable[[Dict[str, Any]], None],
        **kwargs,
    ) -> tuple[str, threading.Event]:
        """
        Fügt Request mit expliziter Priorität zur Queue hinzu.
        priority: 0=INTERRUPT, 1=NEW_TASK, 2=FOLLOWUP

        If priority == 0 (INTERRUPT), cancels active requests for the same dialog_key.

        Returns:
            (request_id, started_event)
        """
        request_id = kwargs.get("trace_id") or str(uuid.uuid4())
        source = kwargs.get("source", "unknown")
        dialog_key = kwargs.get("dialog_key", "")

        # Event das gesetzt wird wenn der Job wirklich anfängt
        started_event = threading.Event()

        # PriorityQueue item: (priority, seq, request_id, message, cfg, kwargs, result_callback, started_event)
        seq = self._next_seq()
        item = (priority, seq, request_id, message, cfg, kwargs, result_callback, started_event)

        # For INTERRUPT: cancel active requests for this dialog_key
        if priority == 0 and dialog_key:
            with self.active_lock:
                for rid, info in list(self.active_requests.items()):
                    if info.get("dialog_key") == dialog_key or info.get("cfg", {}).get("dialog_key") == dialog_key:
                        self.cancelled_requests.add(rid)

        with self.active_lock:
            self.pending_requests[request_id] = item

        self.queue.put(item)

        # Logging
        try:
            from app.tool_engine import tool_store
            tool_store.log("queue_submitted", {
                "request_id": request_id,
                "dialog_key": dialog_key,
                "source": source,
                "priority": priority,
                "queue_size": self.queue.qsize()
            })
        except Exception:
            pass
            
        return request_id, started_event

    def cancel_request(self, request_id: str) -> bool:
        """Markiert einen Request als abgebrochen."""
        with self.active_lock:
            self.cancelled_requests.add(request_id)
            # Falls noch in pending, wird er beim nächsten Loop einfach übersprungen
            return request_id in self.pending_requests or request_id in self.active_requests

    def is_request_cancelled(self, request_id: str) -> bool:
        """Prüft ob ein Request abgebrochen wurde."""
        with self.active_lock:
            return request_id in self.cancelled_requests

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Status-Informationen zur Queue zurück."""
        with self.active_lock:
            active_count = len(self.active_requests)
            active_details = []
            for rid, info in self.active_requests.items():
                active_details.append({
                    "id": rid,
                    "msg": str(info.get("message", ""))[:50],
                    "started_at": info.get("started_at"),
                    "runtime_s": round(time.time() - info.get("started_at", 0), 1) if info.get("started_at") else 0
                })
                
            pending_details = self.get_pending_requests()
            
            return {
                "queue_size": self.queue.qsize(),
                "active_requests": active_count,
                "worker_alive": self.worker_thread.is_alive() if self.worker_thread else False,
                "active_details": active_details,
                "pending_details": pending_details,
            }

    def peek_followup_for_dialog(self, dialog_key: str) -> Optional[str]:
        """
        Wie pop_followup_for_dialog, aber OHNE das Item zu entfernen.
        Für sofortige Acknowledge-Nachrichten während laufender Tool-Calls.
        """
        if not dialog_key:
            return None
        with self.active_lock:
            best_seq = None
            best_msg = None
            for rid, item in list(self.pending_requests.items()):
                try:
                    prio, seq, _rid, msg, _cfg, kwargs_item = item[0], item[1], item[2], item[3], item[4], item[5]
                    dk = kwargs_item.get("dialog_key", "") if isinstance(kwargs_item, dict) else ""
                    src = kwargs_item.get("source", "") if isinstance(kwargs_item, dict) else ""
                    if dk != dialog_key:
                        continue
                    if prio == 0:
                        continue
                    if not str(src).startswith("messenger:"):
                        continue
                    if best_seq is None or seq < best_seq:
                        best_seq = seq
                        best_msg = str(msg)
                except Exception:
                    continue
            return best_msg

    def pop_followup_for_dialog(self, dialog_key: str) -> Optional[str]:
        """
        Pop and return the next pending non-interrupt messenger message for this dialog_key.
        Used by the react loop to inject mid-task user additions into the running loop.

        Only absorbs messenger:* sources (telegram, discord-rest, discord-gateway).
        WebUI/API requests (source="webui" or "api") are NOT absorbed because their
        HTTP callers are blocking on started_event + result_event and would hang.

        Returns the message string, or None if nothing pending.
        """
        if not dialog_key:
            return None
        with self.active_lock:
            # Find oldest (lowest seq) pending messenger item for this dialog_key
            best_seq = None
            best_rid = None
            for rid, item in list(self.pending_requests.items()):
                try:
                    prio, seq, _rid, msg, _cfg, kwargs_item = item[0], item[1], item[2], item[3], item[4], item[5]
                    dk = kwargs_item.get("dialog_key", "") if isinstance(kwargs_item, dict) else ""
                    src = kwargs_item.get("source", "") if isinstance(kwargs_item, dict) else ""
                    if dk != dialog_key:
                        continue
                    if prio == 0:  # INTERRUPT — don't absorb, let it cancel the loop
                        continue
                    # Only fire-and-forget messenger sources (not webui/api which block on result_event)
                    if not str(src).startswith("messenger:"):
                        continue
                    if best_seq is None or seq < best_seq:
                        best_seq = seq
                        best_rid = rid
                except Exception:
                    continue
            if best_rid is None:
                return None
            # Remove from pending and mark as cancelled so queue worker skips it
            item = self.pending_requests.pop(best_rid, None)
            self.cancelled_requests.add(best_rid)
            if item is not None:
                # Set started_event so submit() callers don't hang (messenger submit is fire-and-forget)
                try:
                    item[7].set()  # started_event at index 7
                except Exception:
                    pass
                return str(item[3])  # message at index 3
        return None

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Listet wartende Requests auf (ohne die Queue zu leeren)."""
        pending = []
        with self.active_lock:
            for rid, item in self.pending_requests.items():
                # item: (priority, seq, request_id, message, cfg, kwargs, result_callback, started_event)
                try:
                    _prio, _seq, _rid, msg, _cfg, kwargs_item = item[0], item[1], item[2], item[3], item[4], item[5]
                    pending.append({
                        "id": rid,
                        "msg": str(msg)[:50],
                        "priority": _prio,
                        "source": kwargs_item.get("source", "unknown") if isinstance(kwargs_item, dict) else "unknown",
                    })
                except Exception:
                    pending.append({"id": rid, "msg": "?", "priority": 1, "source": "unknown"})
        return pending

    def _watchdog_loop(self):
        """Überwacht hängende Requests.
        OPT-6: Doppelter except-Block entfernt (war toter Code).
                result_callback wird jetzt aufgerufen damit Caller nicht hängen.
        """
        while not self._watchdog_stop.is_set():
            try:
                with self.active_lock:
                    now = time.time()
                    overdue = []
                    for rid, info in self.active_requests.items():
                        started = info.get("started_at")
                        if started and (now - started) > self._overdue_timeout:
                            overdue.append(rid)
                    
                    for rid in overdue:
                        info = self.active_requests.pop(rid, {})
                        # OPT-6: Callback aufrufen damit der Caller nicht hängt
                        cb = info.get("result_callback")
                        if callable(cb):
                            try:
                                cb({"ok": False, "reply": "⏱ Request-Timeout (Watchdog): Job wurde beendet."})
                            except Exception:
                                pass
                        try:
                            from app.tool_engine import tool_store
                            duration = now - info.get("started_at", now)
                            tool_store.log("queue_watchdog", f"Request {rid[:8]} overdue ({duration:.1f}s), callback notified")
                            tool_store.log("queue_overdue", {
                                "request_id": rid,
                                "duration": duration,
                                "note": "callback_notified",
                            })
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(self._watchdog_interval)

    def _process_queue(self):
        """Worker-Loop: Verarbeitet Requests nacheinander."""
        while not self.stop_event.is_set():
            try:
                try:
                    item = self.queue.get(timeout=0.5)
                    # item: (priority, seq, request_id, message, cfg, kwargs, result_callback, started_event)
                    _priority, _seq, request_id, message, cfg, kwargs, result_callback, started_event = item
                except queue.Empty:
                    continue
                except Exception as e:
                    # This could happen if item is not a tuple of 8
                    try:
                        from app.tool_engine import tool_store
                        tool_store.log("queue_error", f"Invalid item in queue: {e}")
                    except: pass
                    continue

                # Check if cancelled while in queue
                with self.active_lock:
                    if request_id in self.cancelled_requests:
                        self.pending_requests.pop(request_id, None)
                        self.cancelled_requests.remove(request_id)
                        continue
                    
                    # Als aktiv markieren
                    self.active_requests[request_id] = {
                        "message": message,
                        "started_at": time.time(),
                        "cfg": cfg,
                        "dialog_key": kwargs.get("dialog_key", ""),
                    }
                    self.pending_requests.pop(request_id, None)

                # Signal: Job fängt jetzt WIRKLICH an
                started_event.set()

                # Log Start
                try:
                    from app.tool_engine import tool_store
                    tool_store.log("queue_start", {
                        "request_id": request_id,
                        "source": str(kwargs.get("source", "unknown")),
                        "dialog_key": str(kwargs.get("dialog_key", "unknown")),
                        "trace_id": str(kwargs.get("trace_id", "unknown"))
                    })
                except Exception:
                    pass

                # Verarbeitung – läuft in separatem Thread damit der Worker-Thread
                # niemals dauerhaft blockiert werden kann.
                start_t = time.time()
                result = {"ok": False, "reply": "Fehler bei der Verarbeitung"}
                # Timeout für den Reply-Thread: etwas kürzer als der Watchdog-Timeout
                reply_timeout = max(60, self._overdue_timeout - 30)
                try:
                    if self.chat_reply_fn:
                        import queue as _queue_mod
                        _reply_q: "queue.Queue" = _queue_mod.Queue(maxsize=1)

                        def _reply_runner() -> None:
                            try:
                                out = self.chat_reply_fn(message, cfg, **kwargs)
                                try:
                                    _reply_q.put(("ok", out), block=False)
                                except Exception:
                                    pass
                            except Exception as _exc:
                                import traceback as _tb
                                try:
                                    _reply_q.put(("err", _exc, _tb.format_exc()), block=False)
                                except Exception:
                                    pass

                        try:
                            from app.trace_utils import start_thread_with_trace
                            _reply_thread = start_thread_with_trace(
                                _reply_runner,
                                name=f"ChatReplyWorker-{request_id[:8]}",
                                daemon=True,
                            )
                        except Exception:
                            _reply_thread = threading.Thread(
                                target=_reply_runner,
                                daemon=True,
                                name=f"ChatReplyWorker-{request_id[:8]}",
                            )
                            _reply_thread.start()

                        try:
                            payload = _reply_q.get(timeout=reply_timeout)
                            if payload[0] == "ok":
                                result = payload[1]
                            else:
                                _exc = payload[1]
                                _tb_str = payload[2] if len(payload) > 2 else ""
                                error_msg = f"Worker Error: {str(_exc)}\n{_tb_str}"
                                try:
                                    from app.tool_engine import tool_store
                                    tool_store.log("queue_error", f"{request_id[:8]} failed: {str(_exc)}")
                                except Exception:
                                    pass
                                result = {"ok": False, "reply": f"Fehler im Worker: {str(_exc)}", "error": error_msg}
                        except _queue_mod.Empty:
                            # Log Timeout
                            try:
                                from app.tool_engine import tool_store
                                tool_store.log("queue_reply_timeout", {
                                    "request_id": request_id, 
                                    "timeout_s": reply_timeout
                                })
                            except Exception:
                                pass
                            result = {"ok": False, "reply": f"Verarbeitung hat zu lange gedauert (>{reply_timeout}s) – bitte erneut versuchen."}
                    else:
                        result = {"ok": False, "reply": "Keine Reply-Funktion gesetzt"}
                except Exception as e:
                    import traceback
                    error_msg = f"Worker Error: {str(e)}\n{traceback.format_exc()}"
                    try:
                        from app.tool_engine import tool_store
                        tool_store.log("queue_error", f"{request_id[:8]} failed: {str(e)}")
                    except Exception:
                        pass
                    result = {"ok": False, "reply": f"Fehler im Worker: {str(e)}", "error": error_msg}
                finally:
                    duration = time.time() - start_t
                    with self.active_lock:
                        self.active_requests.pop(request_id, None)
                        if request_id in self.cancelled_requests:
                            self.cancelled_requests.remove(request_id)

                    # Log End
                    try:
                        from app.tool_engine import tool_store
                        tool_store.log("queue_end", {
                            "request_id": request_id,
                            "duration_s": duration
                        })
                    except Exception:
                        pass

                    # Callback ausführen
                    if result_callback:
                        try:
                            result_callback(result)
                        except Exception as _cb_exc:
                            try:
                                import traceback as _tb
                                tool_store.log("result_callback_error", {
                                    "request_id": request_id,
                                    "error": str(_cb_exc),
                                    "traceback": _tb.format_exc()
                                })
                            except Exception:
                                pass

                self.queue.task_done()
            except Exception as fatal_exc:
                # Last resort fallback to prevent thread death
                try:
                    from app.tool_engine import tool_store
                    tool_store.log("queue_fatal_error", f"Worker loop iteration failed: {fatal_exc}")
                except:
                    pass
                time.sleep(1)
