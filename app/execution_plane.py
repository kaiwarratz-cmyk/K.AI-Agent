from __future__ import annotations

import contextlib
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import signal
import time
import threading
import traceback
import sys
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

from app.config import ROOT_DIR, load_config
from app.tool_engine import tool_store

def _now_iso() -> str:
    """Lokale ISO-Zeit für Logs."""
    return datetime.now().isoformat()

def _ep_log(message: str) -> None:
    """Strukturierte Log-Ausgabe mit Icons und Lokalzeit."""
    msg_str = str(message or "").strip()
    icon = "⚙️ "
    
    # Event-Typen für bessere Übersicht
    if "job_start" in msg_str: icon = "🚀 "
    elif "job_ok" in msg_str: icon = "✅ "
    elif "job_error" in msg_str: icon = "❌ "
    elif "job_stream" in msg_str: icon = "📺 "
    elif "job_exec_enter" in msg_str: icon = "📥 "
    elif "job_exec_exit" in msg_str: icon = "📤 "
    elif "boot" in msg_str: icon = "🔋 "
    elif "shutdown" in msg_str: icon = "🔌 "
    elif "watchdog" in msg_str: icon = "🐕 "
    
    # Kurz-Zeit für die Konsole
    short_time = datetime.now().strftime("%H:%M:%S")
    
    # Strukturierte Zeile für die Konsole
    # Wir rücken die Nachricht etwas ein, damit die Icons sauber untereinander stehen
    display_line = f"[{short_time}] {icon}{msg_str}"
    try:
        print(display_line, flush=True)
    except Exception:
        pass
    
    try:
        _log_file = (ROOT_DIR / "data" / "logs" / "execution_plane.log").resolve()
        _log_file.parent.mkdir(parents=True, exist_ok=True)
        # Vollständige Zeit für das File-Log
        with _log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"{_now_iso()} {icon}{msg_str}\n")
    except Exception:
        pass

def _execution_cfg() -> Dict[str, Any]:
    cfg = load_config()
    raw = cfg.get("execution_plane", {}) if isinstance(cfg.get("execution_plane", {}), dict) else {}
    return {
        "host": str(os.environ.get("KAI_EXECUTION_HOST", raw.get("host", "127.0.0.1")) or "127.0.0.1").strip(),
        "port": int(os.environ.get("KAI_EXECUTION_PORT", raw.get("port", 8765)) or 8765),
        "auth_token": str(os.environ.get("KAI_EXECUTION_TOKEN", raw.get("auth_token", "")) or "").strip(),
    }

# OPT-4: Config einmalig beim Start cachen – nicht bei JEDEM HTTP-Request laden.
_exec_cfg_cache: Optional[Dict[str, Any]] = None
_exec_cfg_lock = threading.Lock()

def _get_exec_cfg() -> Dict[str, Any]:
    """Gibt die gecachte Execution-Plane-Config zurück.
    Beim ersten Aufruf wird load_config() ausgeführt, danach gecacht.
    """
    global _exec_cfg_cache
    if _exec_cfg_cache is not None:
        return _exec_cfg_cache
    with _exec_cfg_lock:
        if _exec_cfg_cache is None:  # Double-checked locking
            _exec_cfg_cache = _execution_cfg()
    return _exec_cfg_cache

def _invalidate_exec_cfg_cache() -> None:
    """Invalidiert den Config-Cache (z.B. nach save_config())."""
    global _exec_cfg_cache
    _exec_cfg_cache = None


def _auth_required(x_execution_token: str | None) -> None:
    # OPT-4: Nutzt gecachte Config statt bei jedem Request von Disk zu lesen.
    cfg = _get_exec_cfg()
    token = str(cfg.get("auth_token", "") or "").strip()
    if not token:
        return
    got = str(x_execution_token or "").strip()
    if got != token:
        raise HTTPException(status_code=401, detail="invalid_execution_token")


class ExecuteRequest(BaseModel):
    action: Dict[str, Any]
    trace_id: str = ""
    note: str = ""
    source: str = ""
    dialog_key: str = ""

class CancelRequest(BaseModel):
    reason: str = "manual"

class ShutdownRequest(BaseModel):
    reason: str = "manual"

_started_at = _now_iso()
_jobs_lock = Lock()
_running_jobs: Dict[str, Dict[str, Any]] = {}
_recent_jobs: Deque[Dict[str, Any]] = deque(maxlen=300)
_last_error = ""
_log_file = (ROOT_DIR / "data" / "logs" / "execution_plane.log").resolve()

app = FastAPI(title="K.AI Execution Plane", version="1.0.0")

def _action_preview(action: Dict[str, Any]) -> str:
    try:
        if not isinstance(action, dict):
            return "{}"
        out: Dict[str, Any] = {}
        for k, v in action.items():
            key = str(k or "").strip()
            if not key:
                continue
            low = key.lower()
            if low in {"script", "code", "content", "html_body", "body"}:
                out[key] = f"<{len(str(v or ''))} chars>"
                continue
            if low in {"token", "api_key", "password", "secret", "auth_token", "access_token", "refresh_token"}:
                out[key] = "***"
                continue
            if isinstance(v, (bool, int, float)) or v is None:
                out[key] = v
            else:
                txt = str(v)
                txt = " ".join(txt.split())
                out[key] = txt[:120] + ("..." if len(txt) > 120 else "")
        return str(out)
    except Exception:
        return "{}"

def _push_recent(item: Dict[str, Any]) -> None:
    with _jobs_lock:
        _recent_jobs.appendleft(dict(item))

def _running_snapshot() -> List[Dict[str, Any]]:
    with _jobs_lock:
        out: List[Dict[str, Any]] = []
        for v in _running_jobs.values():
            row = dict(v)
            try:
                started = float(row.get("started_ts", 0.0) or 0.0)
                row["runtime_sec"] = max(0.0, round(time.time() - started, 3))
            except Exception:
                row["runtime_sec"] = 0.0
            out.append(row)
        return out

@app.get("/health")
def health(x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    return {
        "ok": True,
        "service": "execution_plane",
        "pid": os.getpid(),
        "started_at": _started_at,
        "running_jobs": len(_running_snapshot()),
    }

@app.get("/stats")
def stats(x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    running = _running_snapshot()
    with _jobs_lock:
        recent_count = len(_recent_jobs)
        last = dict(_recent_jobs[0]) if _recent_jobs else {}
    return {
        "ok": True,
        "pid": os.getpid(),
        "started_at": _started_at,
        "running_jobs": running,
        "running_count": len(running),
        "recent_count": recent_count,
        "last_job": last,
        "last_error": str(_last_error or ""),
    }

@app.get("/jobs/recent")
def jobs_recent(limit: int = 30, x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    lim = max(1, min(300, int(limit)))
    with _jobs_lock:
        items = [dict(x) for x in list(_recent_jobs)[:lim]]
    return {"ok": True, "count": len(items), "items": items}

@app.post("/cancel_running")
def cancel_running(req: CancelRequest, x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    stopped = False
    import app.main as main_mod
    try:
        stopped = bool(main_mod._request_script_stop(reason=f"execution_plane:{str(req.reason or 'manual')}"))  # type: ignore[attr-defined]
    except Exception:
        stopped = False
    _ep_log(f"cancel_running reason={str(req.reason or 'manual')} stopped={bool(stopped)}")
    return {"ok": True, "stopped": bool(stopped)}

@app.post("/shutdown")
def shutdown(req: ShutdownRequest, x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    reason = str(req.reason or "manual").strip() or "manual"
    _ep_log(f"shutdown_requested reason={reason} pid={os.getpid()}")

    def _delayed_exit() -> None:
        time.sleep(0.25)
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGTERM)
        with contextlib.suppress(Exception):
            os._exit(0)

    try:
        from app.trace_utils import start_thread_with_trace
        start_thread_with_trace(_delayed_exit, name="execution-plane-shutdown", daemon=True)
    except Exception:
        threading.Thread(target=_delayed_exit, daemon=True, name="execution-plane-shutdown").start()
    return {"ok": True, "shutting_down": True, "pid": os.getpid(), "reason": reason}

@app.post("/restart")
def restart(req: ShutdownRequest, x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    _auth_required(x_execution_token)
    reason = str(req.reason or "manual").strip() or "manual"
    _ep_log(f"restart_requested reason={reason} pid={os.getpid()}")

    def _delayed_restart() -> None:
        time.sleep(0.25)
        _ep_log(f"restart_spawning_new_process reason={reason}")
        try:
            import subprocess
            import sys
            from pathlib import Path as _Path
            _root = _Path(__file__).parent.parent
            _venv_py = _root / ".venv" / "Scripts" / "python.exe"
            _python_exe = str(_venv_py) if _venv_py.exists() else sys.executable
            cfg = _execution_cfg()
            cmd = [_python_exe, "-m", "app.execution_plane"]
            subprocess.Popen(cmd, start_new_session=True, cwd=str(_root))
        except Exception as exc:
            _ep_log(f"restart_failed to spawn: {exc}")
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGTERM)
        with contextlib.suppress(Exception):
            os._exit(0)

    try:
        from app.trace_utils import start_thread_with_trace
        start_thread_with_trace(_delayed_restart, name="execution-plane-restart", daemon=True)
    except Exception:
        threading.Thread(target=_delayed_restart, daemon=True, name="execution-plane-restart").start()
    return {"ok": True, "restarting": True, "pid": os.getpid(), "reason": reason}

@app.post("/execute")
def execute(req: ExecuteRequest, x_execution_token: str | None = Header(default=None)) -> Dict[str, Any]:
    global _last_error
    _auth_required(x_execution_token)
    action = dict(req.action or {})
    try:
        alias_map = {
            "gmail_send": "gmail_send_email",
            "gmail_send_advanced": "gmail_send_email_advanced",
            "gmail_list": "gmail_list_messages",
        }
        k0 = str(action.get("kind", "") or "").strip()
        if k0 in alias_map:
            action["kind"] = alias_map[k0]
    except Exception:
        pass
    kind = str(action.get("kind", "") or "").strip() or "action"
    job_id = uuid.uuid4().hex[:16]
    started_ts = time.time()
    running_item = {
        "job_id": job_id,
        "kind": kind,
        "trace_id": str(req.trace_id or "").strip(),
        "note": str(req.note or "").strip(),
        "source": str(req.source or "").strip(),
        "dialog_key": str(req.dialog_key or "").strip(),
        "started_at": _now_iso(),
        "started_ts": started_ts,
    }
    with _jobs_lock:
        _running_jobs[job_id] = dict(running_item)
    
    # Strukturierter Start-Log
    _ep_log(f"job_start [{job_id}] kind={kind} source={str(req.source or '-')}")
    _ep_log(f"  └─ trace={str(req.trace_id or '-')[:16]} action={_action_preview(action)}")

    # Watchdog disabled to prevent log spam
    def _job_watchdog(jid: str, thresh: int) -> None:
        pass

    try:
        import app.main as main_mod
        hook_token = None
        hook_set = getattr(main_mod, "_set_script_stream_hook", None)
        hook_reset = getattr(main_mod, "_reset_script_stream_hook", None)
        
        if callable(hook_set) and callable(hook_reset):
            def _progress_hook(event: Dict[str, Any]) -> None:
                stream = str(event.get("stream", "stdout") or "stdout").strip().lower()
                line = str(event.get("line", "") or "").replace("\r", " ").strip()
                if not line: return
                _ep_log(f"job_stream [{job_id}] {stream}: {line[:320]}")
            with contextlib.suppress(Exception):
                hook_token = hook_set(_progress_hook)
                
        kind_handler = None
        try:
            kind_handler = getattr(main_mod, "_skill_handler_for_kind", None)
        except Exception:
            kind_handler = None
            
        if callable(kind_handler) and isinstance(kind_handler(kind), dict):
            _ep_log(f"job_exec_enter [{job_id}] mode=skill")
            try:
                res = main_mod._run_skill_action(load_config(), action)  # type: ignore[attr-defined]
                tool_name = str(action.get("kind", kind))
                reply = str(res.get("reply", "") if isinstance(res, dict) else str(res or ""))
            except Exception as exc:
                tool_name, reply = kind, f"Skill-Execution-Fehler: {exc}"
            _ep_log(f"job_exec_exit [{job_id}] mode=skill")
        else:
            _ep_log(f"job_exec_enter [{job_id}] mode=local")
            try:
                # trace_id NUR für sys_python_exec einbetten → persistente Session pro Job
                # NICHT für andere Tools (fs_write_file etc. kennen trace_id nicht)
                if req.trace_id and action.get("kind") == "sys_python_exec" and not action.get("trace_id"):
                    action["trace_id"] = req.trace_id
                tool_name, reply = main_mod._execute_action_local(action)  # type: ignore[attr-defined]
            except Exception as exc:
                tool_name, reply = kind, f"Local-Execution-Fehler: {exc}"
            _ep_log(f"job_exec_exit [{job_id}] mode=local")
            
        duration_ms = int(max(0.0, (time.time() - started_ts) * 1000.0))
        out = {
            "ok": True,
            "job_id": job_id,
            "tool_name": str(tool_name or kind),
            "reply": str(reply or ""),
            "duration_ms": duration_ms,
        }
        _push_recent({
            "job_id": job_id, "ok": True, "kind": kind, "tool_name": str(tool_name or kind),
            "trace_id": str(req.trace_id or "").strip(), "note": str(req.note or "").strip(),
            "source": str(req.source or "").strip(), "dialog_key": str(req.dialog_key or "").strip(),
            "duration_ms": duration_ms, "reply_preview": str(reply or "")[:500], "created_at": _now_iso(),
        })
        
        reply_short = str(reply or "").replace('\r', '').replace('\n', '\\n')[:180]
        _ep_log(f"job_ok [{job_id}] duration={duration_ms}ms reply={reply_short}")
        return out
        
    except Exception as exc:
        _last_error = str(exc)
        tb = traceback.format_exc(limit=5)
        duration_ms = int(max(0.0, (time.time() - started_ts) * 1000.0))
        _push_recent({
            "job_id": job_id, "ok": False, "kind": kind, "tool_name": kind,
            "trace_id": str(req.trace_id or "").strip(), "note": str(req.note or "").strip(),
            "source": str(req.source or "").strip(), "dialog_key": str(req.dialog_key or "").strip(),
            "duration_ms": duration_ms, "error": str(exc), "traceback": str(tb)[-2000:], "created_at": _now_iso(),
        })
        tool_store.log("execution_plane_error", f"{kind}: {exc}")
        _ep_log(f"job_error [{job_id}] error={str(exc)[:260]}")
        return {"ok": False, "job_id": job_id, "tool_name": kind, "error": str(exc), "traceback": str(tb)[-3000:]}
    finally:
        with contextlib.suppress(Exception):
            if "hook_token" in locals() and hook_token is not None:
                hook_reset = locals().get("hook_reset")
                if callable(hook_reset): hook_reset(hook_token)
        with _jobs_lock:
            _running_jobs.pop(job_id, None)

if __name__ == "__main__":
    cfg = _execution_cfg()
    host = str(cfg.get("host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    port = max(1024, min(65535, int(cfg.get("port", 8765) or 8765)))
    _ep_log(f"boot host={host} port={port} pid={os.getpid()}")
    uvicorn.run("app.execution_plane:app", host=host, port=port, reload=False, log_level="warning")
