from __future__ import annotations

import subprocess
import tempfile
import threading
import time
import queue
import re
from pathlib import Path
from typing import Dict, Optional


_ROOT_DIR = Path(__file__).parent.parent.parent
_VENV_PYTHON = _ROOT_DIR / ".venv" / "Scripts" / "python.exe"
_PYTHON_EXE = str(_VENV_PYTHON.resolve()) if _VENV_PYTHON.exists() else "python"

# Modul-Level Stop-Event: wird von main.py beim Job-Abort gesetzt.
# Erlaubt sofortigen Abbruch laufender Python-Scripts ohne auf Timeout warten zu müssen.
_stop_event: threading.Event = threading.Event()

# ─── Persistente Session-Registry ────────────────────────────────────────────
# Jeder Job (trace_id) bekommt optional eine langlebige Python-REPL-Session,
# so dass Variablen, Imports und Auth-State zwischen sys_python_exec-Calls erhalten bleiben.

_python_sessions: Dict[str, "PersistentSession"] = {}
_python_sessions_lock = threading.Lock()

# REPL-Skript das als persistenter Python-Prozess läuft
_REPL_SCRIPT = r"""
import sys
import io
import os
import traceback as _tb

# ── CWD-Anker: Agent arbeitet IMMER im K.AI-Root ─────────────────────────────
_KAIAI_ROOT = os.environ.get('KAIAI_ROOT', '')
if _KAIAI_ROOT and os.path.isdir(_KAIAI_ROOT):
    try:
        os.chdir(_KAIAI_ROOT)
    except Exception:
        pass
# ─────────────────────────────────────────────────────────────────────────────

_ns = {"__name__": "__main__"}
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

while True:
    try:
        line = sys.stdin.readline()
    except Exception:
        break
    if not line:
        break
    cmd = line.rstrip('\r\n')
    if cmd == '###KAIAI_EXIT###':
        break
    if cmd == '###KAIAI_CODE_START###':
        code_lines = []
        while True:
            cl = sys.stdin.readline()
            if not cl or cl.rstrip('\r\n') == '###KAIAI_CODE_END###':
                break
            code_lines.append(cl)
        code = ''.join(code_lines)
        # ── CWD-Guard: vor jedem Block sicherstellen dass wir im Root sind ────
        if _KAIAI_ROOT and os.path.isdir(_KAIAI_ROOT):
            try:
                os.chdir(_KAIAI_ROOT)
            except Exception:
                pass
        # ─────────────────────────────────────────────────────────────────────
        old_out = sys.stdout
        old_err = sys.stderr
        sys.stdout = _ob = io.StringIO()
        sys.stderr = _eb = io.StringIO()
        _rc = 0
        try:
            import ast
            parsed_ast = ast.parse(code, '<cell>', 'exec')
            if parsed_ast.body and isinstance(parsed_ast.body[-1], ast.Expr):
                last_expr = parsed_ast.body.pop()
                if parsed_ast.body:
                    exec(compile(parsed_ast, '<cell>', 'exec'), _ns)
                _res = eval(compile(ast.Expression(last_expr.value), '<cell>', 'eval'), _ns)
                if _res is not None:
                    print(repr(_res))
            else:
                exec(compile(code, '<cell>', 'exec'), _ns)
        except SystemExit as e:
            _rc = int(e.code) if isinstance(e.code, int) else (1 if e.code else 0)
        except SyntaxError as e:
            _eb.write(f"SyntaxError: {e.msg} an Zeile {e.lineno}\n")
            _rc = 1
        except Exception:
            _eb.write(_tb.format_exc())
            _rc = 1
            try:
                sys.stderr.flush()
            except Exception:
                pass
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
        sys.stdout.write('###KAIAI_STDOUT_START###\n')
        sys.stdout.write(_ob.getvalue())
        sys.stdout.write('\n###KAIAI_STDOUT_END###\n')
        sys.stdout.write('###KAIAI_STDERR_START###\n')
        sys.stdout.write(_eb.getvalue())
        sys.stdout.write('\n###KAIAI_STDERR_END###\n')
        sys.stdout.write('returncode={}\n'.format(_rc))
        sys.stdout.write('###KAIAI_DONE###\n')
        sys.stdout.flush()
        sys.stderr.flush()
"""


class PersistentSession:
    """Langlebige Python-REPL-Session für einen Job.
    Variablen, Imports und Auth-State bleiben zwischen sys_python_exec-Calls erhalten.
    """

    def __init__(self) -> None:
        import os
        import base64

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(_REPL_SCRIPT)
            self._script = Path(f.name)

        ps_cmd = f"& '{_PYTHON_EXE}' '{str(self._script)}'"
        encoded = base64.b64encode(ps_cmd.encode("utf-16-le")).decode("ascii")

        workspace = (_ROOT_DIR / "data" / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        root_str = str(_ROOT_DIR.resolve())

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root_str + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["KAIAI_WORKSPACE"] = str(workspace)
        env["KAIAI_ROOT"] = root_str
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"

        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_str,
            env=env,
        )

    def execute(self, code: str, stop_event: threading.Event, timeout: int) -> Dict:
        if self.proc.poll() is not None:
            return {"returncode": -1, "stdout": "", "stderr": "Session nicht mehr aktiv.", "python_exe": _PYTHON_EXE}

        try:
            self.proc.stdin.write("###KAIAI_CODE_START###\n")
            self.proc.stdin.write(code if code.endswith("\n") else code + "\n")
            self.proc.stdin.write("###KAIAI_CODE_END###\n")
            self.proc.stdin.flush()
        except Exception as e:
            return {"returncode": -1, "stdout": "", "stderr": f"Write fehlgeschlagen: {e}", "python_exe": _PYTHON_EXE}

        # Nicht-blockierendes Lesen via Thread + Queue
        out_q: queue.Queue = queue.Queue()

        def _reader():
            try:
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        break
                    out_q.put(line)
                    if line.rstrip("\r\n") == "###KAIAI_DONE###":
                        break
            except Exception:
                pass

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        lines = []
        elapsed = 0.0
        while True:
            if stop_event and stop_event.is_set():
                self.close()
                return {"returncode": -9, "stdout": "", "stderr": "Aborted.", "python_exe": _PYTHON_EXE}
            try:
                line = out_q.get(timeout=0.2)
                lines.append(line)
                if line.rstrip("\r\n") == "###KAIAI_DONE###":
                    break
            except queue.Empty:
                elapsed += 0.2
                if elapsed >= timeout:
                    return {
                        "returncode": -124,
                        "stdout": "".join(lines),
                        "stderr": f"Timeout nach {timeout}s.",
                        "python_exe": _PYTHON_EXE,
                    }

        t.join(timeout=1)
        full = "".join(lines)

        def _between(text: str, start: str, end: str) -> str:
            s = text.find(start)
            e = text.find(end)
            if s == -1 or e == -1:
                return ""
            return text[s + len(start):e].strip("\n")

        rc_m = re.search(r"returncode=(-?\d+)", full)
        stdout = _between(full, "###KAIAI_STDOUT_START###\n", "\n###KAIAI_STDOUT_END###")
        stderr = _between(full, "###KAIAI_STDERR_START###\n", "\n###KAIAI_STDERR_END###")
        
        # 🚨 Fallback: Wenn keine Marker gefunden (harter Crash), nimm alles als stderr
        if not stdout and not stderr and full.strip():
            stderr = f"CRITICAL: REPL-Markers missing. Raw output:\n{full.strip()}"

        return {
            "returncode": int(rc_m.group(1)) if rc_m else -1,
            "stdout": stdout,
            "stderr": stderr,
            "python_exe": _PYTHON_EXE,
        }

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write("###KAIAI_EXIT###\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=2)
        except Exception:
            pass
        try:
            if self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        try:
            self._script.unlink(missing_ok=True)
        except Exception:
            pass


def cleanup_session(trace_id: str) -> None:
    """Beendet die persistente Python-Session eines Jobs. Wird bei Job-Ende aufgerufen."""
    with _python_sessions_lock:
        session = _python_sessions.pop(trace_id, None)
    if session:
        session.close()


def run_python(
    code: str,
    timeout_sec: int = 0,  # Ignoriert – Timeout kommt ausschließlich aus der Konfiguration (max_step_timeout_sec)
    trace_id: str = "",    # Job-ID: wenn gesetzt, wird persistente Session verwendet
    **_ignored_kwargs,     # Unbekannte LLM-Parameter sicher ignorieren
) -> Dict[str, str | int]:
    # Timeout: ausschließlich aus der WebUI-Konfiguration (max_step_timeout_sec).
    # Das LLM setzt keinen Timeout – alle Zeitlimits werden zentral über das WebUI gesteuert.
    try:
        from pathlib import Path as _Path
        import json as _json
        _cfg_path = _Path(__file__).parent.parent.parent / "data" / "config.json"
        _cfg = _json.loads(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.exists() else {}
        effective_timeout = max(30, int(_cfg.get("cli_core", {}).get("max_step_timeout_sec", 600) or 600))
    except Exception:
        effective_timeout = 600

    # PRE-FLIGHT SYNTAX CHECK (Stage 2)
    # Bevor wir den Python-Prozess belasten (egal ob Session oder Stateless),
    # prüfen wir wie Claude Code aktiv auf rudimentäre Syntax-Fehler.
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {
            "returncode": 1, 
            "stdout": "", 
            "stderr": f"LINTER ERROR (Pre-Flight):\nSyntaxError in Zeile {e.lineno}: {e.msg}\n{e.text or ''}\nCode wurde präventiv NICHT ausgeführt. Bitte Syntax korrigieren.", 
            "python_exe": _PYTHON_EXE
        }
        

    # Persistente Session: wenn trace_id vorhanden, Session wiederverwenden oder neu erstellen
    if trace_id:
        with _python_sessions_lock:
            session = _python_sessions.get(trace_id)
            if session is None or session.proc.poll() is not None:
                session = PersistentSession()
                _python_sessions[trace_id] = session
        return session.execute(code, _stop_event, effective_timeout)

    # Fallback: stateless Ausführung (kein trace_id → z.B. direkte API-Aufrufe)
    import os
    import base64

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = Path(f.name)
    workspace = (_ROOT_DIR / "data" / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    root_dir = _ROOT_DIR.resolve()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    root_str = str(root_dir)
    env["PYTHONPATH"] = root_str + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["KAIAI_WORKSPACE"] = str(workspace)
    env["KAIAI_ROOT"] = root_str
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    proc = None
    try:
        ps_cmd = f"& '{_PYTHON_EXE}' '{str(tmp_path)}'"
        encoded = base64.b64encode(ps_cmd.encode("utf-16-le")).decode("ascii")
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_str,
            env=env,
        )

        def _read_stream(stream, chunks):
            try:
                for line in stream:
                    chunks.append(line)
            except Exception:
                pass

        t_out = threading.Thread(target=_read_stream, args=(proc.stdout, stdout_chunks), daemon=True)
        t_err = threading.Thread(target=_read_stream, args=(proc.stderr, stderr_chunks), daemon=True)
        t_out.start()
        t_err.start()

        elapsed = 0
        while True:
            try:
                proc.wait(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                elapsed += 1
                if _stop_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
                if elapsed >= effective_timeout:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break

        t_out.join(timeout=2)
        t_err.join(timeout=2)
        return {
            "returncode": proc.returncode if proc.returncode is not None else -1,
            "stdout": "".join(stdout_chunks),
            "stderr": "".join(stderr_chunks),
            "python_exe": _PYTHON_EXE,
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


# wrap run_python for logging/validation
try:
    from app.tools.wrapper import validated_tool

    run_python = validated_tool("python.run_python", None)(run_python)
except Exception:
    pass
