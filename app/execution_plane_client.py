from __future__ import annotations

import contextlib
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app.config import ROOT_DIR, save_config


LogFn = Callable[[str], None]

# Always use venv Python to avoid spawning system Python accidentally
_VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
_PYTHON_EXE = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


class ExecutionPlaneClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen[str]] = None
        self._started_by_us = False
        self._last_error = ""
        self._last_started_at = 0.0

    @staticmethod
    def is_execution_plane_process() -> bool:
        return str(os.environ.get("KAI_EXECUTION_PLANE_PROCESS", "")).strip() == "1"

    @staticmethod
    def _cfg_exec(cfg: Dict[str, Any]) -> Dict[str, Any]:
        raw = cfg.get("execution_plane", {}) if isinstance(cfg.get("execution_plane", {}), dict) else {}
        out: Dict[str, Any] = {
            "enabled": bool(raw.get("enabled", True)),
            "host": str(raw.get("host", "127.0.0.1") or "127.0.0.1").strip(),
            "port": int(raw.get("port", 8765) or 8765),
            "auth_token": str(raw.get("auth_token", "") or "").strip(),
            "auto_start": bool(raw.get("auto_start", True)),
            "show_console": bool(raw.get("show_console", True)),
            "request_timeout_sec": int(raw.get("request_timeout_sec", 1800) or 1800),
            "fallback_to_local": bool(raw.get("fallback_to_local", True)),
        }
        out["port"] = max(1024, min(65535, int(out["port"])))
        out["request_timeout_sec"] = max(10, min(7200, int(out["request_timeout_sec"])))
        return out

    @staticmethod
    def _base_url(exec_cfg: Dict[str, Any]) -> str:
        host = str(exec_cfg.get("host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
        port = int(exec_cfg.get("port", 8765) or 8765)
        return f"http://{host}:{port}"

    @staticmethod
    def _headers(exec_cfg: Dict[str, Any]) -> Dict[str, str]:
        token = str(exec_cfg.get("auth_token", "") or "").strip()
        if not token:
            return {}
        return {"X-Execution-Token": token}

    def _request(
        self,
        exec_cfg: Dict[str, Any],
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        timeout_sec: float = 8.0,
    ) -> Dict[str, Any]:
        url = self._base_url(exec_cfg).rstrip("/") + path
        with httpx.Client(timeout=timeout_sec, trust_env=False) as client:
            r = client.request(
                method=method.upper().strip(),
                url=url,
                headers=self._headers(exec_cfg),
                json=json_payload,
            )
            r.raise_for_status()
            body = r.json()
            return body if isinstance(body, dict) else {"ok": False, "error": "invalid_response"}

    def _ensure_token(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        exec_cfg = cfg.setdefault("execution_plane", {}) if isinstance(cfg.setdefault("execution_plane", {}), dict) else {}
        token = str(exec_cfg.get("auth_token", "") or "").strip()
        if token:
            return cfg
        exec_cfg["auth_token"] = secrets.token_urlsafe(24)
        save_config(cfg)
        return cfg

    def health(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        exec_cfg = self._cfg_exec(cfg)
        if not bool(exec_cfg.get("enabled", True)):
            return {"ok": False, "enabled": False, "reason": "disabled"}
        try:
            body = self._request(exec_cfg, "GET", "/health", timeout_sec=3.0)
            if isinstance(body, dict):
                body.setdefault("ok", True)
                body["enabled"] = True
                return body
            return {"ok": False, "enabled": True, "reason": "invalid_response"}
        except Exception as exc:
            return {"ok": False, "enabled": True, "reason": str(exc)}

    def stats(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        exec_cfg = self._cfg_exec(cfg)
        if not bool(exec_cfg.get("enabled", True)):
            return {"ok": False, "enabled": False, "reason": "disabled"}
        try:
            body = self._request(exec_cfg, "GET", "/stats", timeout_sec=4.0)
            if isinstance(body, dict):
                body.setdefault("ok", True)
                body["enabled"] = True
                return body
        except Exception as exc:
            return {"ok": False, "enabled": True, "reason": str(exc)}
        return {"ok": False, "enabled": True, "reason": "invalid_response"}

    def recent_jobs(self, cfg: Dict[str, Any], limit: int = 30) -> Dict[str, Any]:
        exec_cfg = self._cfg_exec(cfg)
        if not bool(exec_cfg.get("enabled", True)):
            return {"ok": False, "enabled": False, "reason": "disabled", "items": []}
        lim = max(1, min(200, int(limit)))
        try:
            body = self._request(exec_cfg, "GET", f"/jobs/recent?limit={lim}", timeout_sec=4.0)
            if isinstance(body, dict):
                body.setdefault("ok", True)
                body["enabled"] = True
                return body
        except Exception as exc:
            return {"ok": False, "enabled": True, "reason": str(exc), "items": []}
        return {"ok": False, "enabled": True, "reason": "invalid_response", "items": []}

    def request_cancel_running(self, cfg: Dict[str, Any], reason: str = "manual") -> bool:
        exec_cfg = self._cfg_exec(cfg)
        if not bool(exec_cfg.get("enabled", True)):
            return False
        try:
            body = self._request(
                exec_cfg,
                "POST",
                "/cancel_running",
                json_payload={"reason": str(reason or "manual")},
                timeout_sec=3.0,
            )
            return bool(body.get("ok", False)) and bool(body.get("stopped", False))
        except Exception:
            return False

    def request_shutdown(self, cfg: Dict[str, Any], reason: str = "manual") -> bool:
        exec_cfg = self._cfg_exec(cfg)
        try:
            body = self._request(
                exec_cfg,
                "POST",
                "/shutdown",
                json_payload={"reason": str(reason or "manual")},
                timeout_sec=3.0,
            )
            return bool(body.get("ok", False))
        except Exception:
            return False

    def execute_action(
        self,
        cfg: Dict[str, Any],
        action: Dict[str, Any],
        *,
        trace_id: str = "",
        note: str = "",
        source: str = "",
        dialog_key: str = "",
    ) -> Tuple[str, str]:
        exec_cfg = self._cfg_exec(cfg)
        timeout_sec = float(exec_cfg.get("request_timeout_sec", 1800) or 1800)
        payload = {
            "action": dict(action or {}),
            "trace_id": str(trace_id or "").strip(),
            "note": str(note or "").strip(),
            "source": str(source or "").strip(),
            "dialog_key": str(dialog_key or "").strip(),
        }
        body = self._request(exec_cfg, "POST", "/execute", json_payload=payload, timeout_sec=timeout_sec)
        if not bool(body.get("ok", False)):
            err = str(body.get("error", "") or body.get("reply", "") or "Execution-Plane Fehler").strip()
            raise RuntimeError(err)
        tool_name = str(body.get("tool_name", "") or str(action.get("kind", "action"))).strip()
        reply = str(body.get("reply", "") or "").strip()
        return tool_name, reply

    def ensure_started(self, cfg: Dict[str, Any], log_fn: Optional[LogFn] = None) -> bool:
        if self.is_execution_plane_process():
            return False
        cfg = self._ensure_token(cfg)
        exec_cfg = self._cfg_exec(cfg)
        if not bool(exec_cfg.get("enabled", True)):
            return False
        h = self.health(cfg)
        if bool(h.get("ok", False)):
            return True
        if not bool(exec_cfg.get("auto_start", True)):
            self._last_error = str(h.get("reason", "not_running"))
            return False

        with self._lock:
            h2 = self.health(cfg)
            if bool(h2.get("ok", False)):
                return True
            if self._proc and self._proc.poll() is None:
                return True
            cmd = [_PYTHON_EXE, "-m", "app.execution_plane"]
            env = os.environ.copy()
            env["KAI_EXECUTION_PLANE_PROCESS"] = "1"
            env["KAI_EXECUTION_HOST"] = str(exec_cfg.get("host", "127.0.0.1"))
            env["KAI_EXECUTION_PORT"] = str(exec_cfg.get("port", 8765))
            env["KAI_EXECUTION_TOKEN"] = str(exec_cfg.get("auth_token", ""))
            show_console = bool(exec_cfg.get("show_console", True))
            # Use CREATE_NEW_CONSOLE so self._proc tracks the actual Python
            # process (not a short-lived cmd.exe wrapper). This prevents
            # ensure_running() from re-spawning when cmd.exe exits quickly.
            creationflags = int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0)) if (os.name == "nt" and show_console) else 0
            stdout = None if show_console else subprocess.DEVNULL
            stderr = None if show_console else subprocess.DEVNULL
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(ROOT_DIR),
                    env=env,
                    stdout=stdout,
                    stderr=stderr,
                    creationflags=creationflags,
                    text=True,
                )
                self._started_by_us = True
                self._last_started_at = time.time()
            except Exception as exc:
                self._last_error = str(exc)
                if callable(log_fn):
                    log_fn(f"Execution-Plane Start fehlgeschlagen: {exc}")
                return False

        deadline = time.time() + 25.0
        while time.time() < deadline:
            h3 = self.health(cfg)
            if bool(h3.get("ok", False)):
                self._last_error = ""
                if callable(log_fn):
                    log_fn("Execution-Plane gestartet.")
                return True
            time.sleep(0.35)
        self._last_error = "health_timeout"
        if callable(log_fn):
            log_fn("Execution-Plane reagiert nicht nach Start.")
        return False

    def stop(self, cfg: Optional[Dict[str, Any]] = None, log_fn: Optional[LogFn] = None) -> None:
        remote_stop_requested = False
        cfg_for_remote = cfg if isinstance(cfg, dict) else None
        if cfg_for_remote is not None:
            with contextlib.suppress(Exception):
                remote_stop_requested = bool(self.request_shutdown(cfg_for_remote, reason="client_stop"))

        with self._lock:
            proc = self._proc
            started_by_us = self._started_by_us
            self._proc = None
            self._started_by_us = False

        local_stopped = False
        if proc and started_by_us and proc.poll() is None:
            with contextlib.suppress(Exception):
                proc.terminate()
            try:
                proc.wait(timeout=6.0)
                local_stopped = True
            except Exception:
                with contextlib.suppress(Exception):
                    proc.kill()
                local_stopped = True

        remote_stopped = False
        if cfg_for_remote is not None and remote_stop_requested:
            deadline = time.time() + 8.0
            while time.time() < deadline:
                h = self.health(cfg_for_remote)
                if not bool(h.get("ok", False)):
                    remote_stopped = True
                    break
                time.sleep(0.25)

        if callable(log_fn):
            if remote_stop_requested and remote_stopped:
                log_fn("Execution-Plane gestoppt (remote shutdown).")
            elif local_stopped:
                log_fn("Execution-Plane gestoppt (lokaler Prozess).")
            elif remote_stop_requested:
                log_fn("Execution-Plane shutdown angefordert, Prozess antwortet noch.")
            else:
                log_fn("Execution-Plane Stop ohne laufenden lokalen Prozess ausgefuehrt.")

    def runtime_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            proc = self._proc
            running = bool(proc and proc.poll() is None)
            pid = int(proc.pid) if proc and running and proc.pid else 0
            return {
                "running": running,
                "pid": pid,
                "started_by_us": bool(self._started_by_us),
                "last_error": str(self._last_error or ""),
                "last_started_at": float(self._last_started_at or 0.0),
            }

    def restart(self, cfg: Dict[str, Any], log_fn: Optional[LogFn] = None) -> bool:
        self.stop(cfg, log_fn=log_fn)
        return self.ensure_started(cfg, log_fn=log_fn)
