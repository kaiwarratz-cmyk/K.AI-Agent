import subprocess
import threading
import time
import uuid
import queue
import os
from typing import Dict, Any, Optional

# Registry für laufende Hintergrundprozesse
_background_processes: Dict[str, Dict[str, Any]] = {}
_processes_lock = threading.Lock()

def terminal_background_run(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    Startet einen persistenten Hintergrundprozess (z.B. ein Server).
    Gibt eine process_id zurück, die für I/O verwendet werden kann.
    """
    proc_id = uuid.uuid4().hex[:12]
    out_q = queue.Queue()
    
    # Environment anreichern
    from app.config import ROOT_DIR
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    _cwd = cwd or str((ROOT_DIR / "data" / "workspace").resolve())
    os.makedirs(_cwd, exist_ok=True)

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stdout/stderr
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_cwd,
            env=env,
            bufsize=1 # Line buffered
        )
        
        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    out_q.put(line)
            except Exception:
                pass
            finally:
                out_q.put(None) # Sentinel for EOF

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()

        with _processes_lock:
            _background_processes[proc_id] = {
                "proc": proc,
                "out_q": out_q,
                "thread": thread,
                "command": command,
                "started_at": time.time(),
                "log": [] # Persistent log cache
            }

        return {
            "ok": True,
            "process_id": proc_id,
            "message": f"Hintergrundprozess gestartet (PID={proc.pid}). Nutze terminal_read_output(process_id='{proc_id}') zum Überwachen."
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def terminal_read_output(process_id: str, timeout: float = 0.5) -> Dict[str, Any]:
    """
    Liest den aktuellen Output (stdout/stderr) eines Hintergrundprozesses.
    Leert die Queue der neuen Zeilen.
    """
    with _processes_lock:
        p_data = _background_processes.get(process_id)
    
    if not p_data:
        return {"ok": False, "error": f"Prozess ID {process_id} nicht gefunden."}
    
    lines = []
    q = p_data["out_q"]
    
    # Warte kurz auf erste Zeile falls leer
    try:
        if q.empty():
            line = q.get(timeout=timeout)
            if line is not None:
                lines.append(line)
                p_data["log"].append(line)
        
        while not q.empty():
            line = q.get_nowait()
            if line is None: break # EOF
            lines.append(line)
            p_data["log"].append(line)
    except queue.Empty:
        pass
    
    status = "running" if p_data["proc"].poll() is None else f"exited (code={p_data['proc'].returncode})"
    
    return {
        "ok": True,
        "status": status,
        "output": "".join(lines),
        "total_log_lines": len(p_data["log"])
    }

def terminal_send_input(process_id: str, text: str) -> Dict[str, Any]:
    """Sendet Standard-Input an einen Hintergrundprozess."""
    with _processes_lock:
        p_data = _background_processes.get(process_id)
    
    if not p_data:
        return {"ok": False, "error": f"Prozess ID {process_id} nicht gefunden."}
    
    if p_data["proc"].poll() is not None:
        return {"ok": False, "error": "Prozess ist bereits beendet."}
        
    try:
        p_data["proc"].stdin.write(text if text.endswith("\n") else text + "\n")
        p_data["proc"].stdin.flush()
        return {"ok": True, "message": "Input gesendet."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def terminal_terminate(process_id: str) -> Dict[str, Any]:
    """Beendet einen Hintergrundprozess hart."""
    with _processes_lock:
        p_data = _background_processes.get(process_id)
    
    if not p_data:
        return {"ok": False, "error": f"Prozess ID {process_id} nicht gefunden."}
    
    proc = p_data["proc"]
    try:
        # Auf Windows den kompletten Baum killen
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
        with _processes_lock:
            _background_processes.pop(process_id, None)
        return {"ok": True, "message": "Prozess erfolgreich beendet."}
    except Exception as e:
        try:
            proc.kill()
            with _processes_lock:
                _background_processes.pop(process_id, None)
            return {"ok": True, "message": f"Prozess via os.kill beendet. (Fehler bei taskkill: {e})"}
        except Exception as e2:
            return {"ok": False, "error": f"Kill fehlgeschlagen: {e2}"}

def terminal_get_all_crashes() -> Dict[str, Any]:
    """
    Sammelt alle Hintergrundprozesse, die abgestuerzt sind (Exit Code != 0).
    """
    crashes = []
    with _processes_lock:
        for pid, p_data in _background_processes.items():
            rc = p_data["proc"].poll()
            if rc is not None and rc != 0:
                # Abgestuerzt
                # Versuche noch restlichen Output zu lesen
                q = p_data["out_q"]
                while not q.empty():
                    line = q.get_nowait()
                    if line: p_data["log"].append(line)
                
                log = "".join(p_data["log"][-20:]) # Letzte 20 Zeilen Log
                crashes.append({
                    "process_id": pid,
                    "command": p_data["command"],
                    "returncode": rc,
                    "last_log": log
                })
        
    return {"ok": True, "crashes": crashes}
