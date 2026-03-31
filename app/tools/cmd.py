from __future__ import annotations

import subprocess
import threading
import time
from typing import Dict


def run_cmd(command: str, timeout: int = 120) -> Dict[str, str | int]:
    """
    Führt einen cmd.exe Befehl aus und gibt stdout/stderr/returncode zurück.

    Verbessert gegenüber subprocess.run():
    - Prüft alle 0.2s auf _script_stop_event (Cancel via /stop oder Job-Abbruch)
    - Killt bei Cancel/Timeout den kompletten Prozessbaum via taskkill /F /T /PID
      (statt nur die Shell zu killen — Kind-Prozesse überleben sonst als Orphans)
    """
    try:
        # Stop-Event aus main.py importieren (late import — vermeidet circular imports)
        try:
            from app.main import _script_stop_event as _stop_ev
        except Exception:
            _stop_ev = None

        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="cp850",
            errors="replace",
        )

        def _force_kill(p: subprocess.Popen) -> None:
            """Killt den kompletten Prozessbaum (Shell + alle Kind-Prozesse)."""
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                    capture_output=True,
                    timeout=8,
                )
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            try:
                p.wait(timeout=5)
            except Exception:
                pass

        out_chunks: list[str] = []
        err_chunks: list[str] = []

        def _read(pipe, buf: list[str]) -> None:
            try:
                for line in pipe:
                    buf.append(line)
            except Exception:
                pass

        t_out = threading.Thread(target=_read, args=(proc.stdout, out_chunks), daemon=True)
        t_err = threading.Thread(target=_read, args=(proc.stderr, err_chunks), daemon=True)
        t_out.start()
        t_err.start()

        started = time.time()
        while proc.poll() is None:
            # Cancel: _script_stop_event gesetzt → sofort beenden (Prozessbaum killen)
            if _stop_ev is not None and _stop_ev.is_set():
                _force_kill(proc)
                t_out.join(timeout=1.5)
                t_err.join(timeout=1.5)
                return {
                    "returncode": -9,
                    "stdout": "".join(out_chunks),
                    "stderr": "ABGEBROCHEN: Job wurde vom Nutzer abgebrochen.",
                }
            # Timeout
            if time.time() - started > timeout:
                _force_kill(proc)
                t_out.join(timeout=1.5)
                t_err.join(timeout=1.5)
                return {
                    "returncode": -124,
                    "stdout": "".join(out_chunks),
                    "stderr": f"TIMEOUT: Befehl nach {timeout}s abgebrochen.",
                }
            time.sleep(0.2)

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        return {
            "returncode": proc.returncode if proc.returncode is not None else -1,
            "stdout": "".join(out_chunks),
            "stderr": "".join(err_chunks),
        }

    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": f"FEHLER: {e}"}


try:
    from app.tools.wrapper import validated_tool
    run_cmd = validated_tool("cmd.run_cmd", None)(run_cmd)
except Exception:
    pass
