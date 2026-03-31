from __future__ import annotations

import threading
import asyncio
import concurrent.futures
import time
from typing import Any, Callable, Optional

# Global event loop for sync-over-async calls
_loop_thread: Optional[threading.Thread] = None
_global_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()

def _ensure_loop():
    global _loop_thread, _global_loop
    with _loop_lock:
        if _global_loop is None:
            _global_loop = asyncio.new_event_loop()
            _loop_thread = threading.Thread(
                target=_global_loop.run_forever, 
                name="SyncCoroLoop", 
                daemon=True
            )
            _loop_thread.start()
            # Give it a moment to start
            time.sleep(0.1)

def _get_current_trace() -> Optional[str]:
    try:
        from app.main import _current_trace_id
        tid = str(_current_trace_id() or "").strip()
        return tid or None
    except Exception:
        return None


def start_thread_with_trace(
    target: Callable[..., Any],
    *args,
    name: Optional[str] = None,
    daemon: bool = True,
    **kwargs,
) -> threading.Thread:
    """Startet einen Thread und setzt vor Aufruf des Targets die aktuelle trace_id (falls vorhanden)."""
    trace = _get_current_trace()

    def _wrapped(*a, **kw):
        if trace:
            try:
                from app.main import _trace_id_ctx
                _trace_id_ctx.set(str(trace))
            except Exception:
                pass
        return target(*a, **kw)

    t = threading.Thread(target=_wrapped, args=args, kwargs=kwargs, name=name, daemon=daemon)
    t.start()
    return t

def run_coro_sync(coro, timeout: Optional[float] = 60.0) -> Any:
    """Runs a coroutine synchronously using a dedicated background event loop."""
    _ensure_loop()
    
    # Schedule the coroutine on the global background loop
    future = asyncio.run_coroutine_threadsafe(coro, _global_loop)
    
    try:
        return future.result(timeout=timeout)
    except Exception:
        future.cancel()
        raise
