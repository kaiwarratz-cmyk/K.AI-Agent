from __future__ import annotations

import base64
import subprocess
from typing import Dict


def shell_command(script: str, timeout: int = 120) -> Dict[str, Any]:
    try:
        # UTF-16-LE Base64-Encoding verhindert Fehler bei Pipes, Anführungszeichen,
        # $-Variablen und mehrzeiligen Skripten (Fix 1 – EncodedCommand)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-EncodedCommand", encoded],
            capture_output=True,
            timeout=timeout,
        )
        
        # Robustes Decoding
        stdout = ""
        stderr = ""
        for enc in ["utf-8", "cp850", "iso-8859-1"]:
            try:
                if not stdout and proc.stdout: stdout = proc.stdout.decode(enc)
                if not stderr and proc.stderr: stderr = proc.stderr.decode(enc)
                if (not proc.stdout or stdout) and (not proc.stderr or stderr): break
            except UnicodeDecodeError:
                continue
        
        stdout = stdout.strip()
        stderr = stderr.strip()
        ok = (proc.returncode == 0)
        
        # Strukturiertes Feedback für das LLM
        if not ok:
            reply = f"[Exit Code {proc.returncode}]\n"
            if stderr:
                reply += f"Fehler (stderr):\n{stderr}\n"
            if stdout:
                reply += f"Teil-Ausgabe (stdout):\n{stdout}"
            if not stderr and not stdout:
                reply += "Befehl schlug ohne Fehlermeldung fehl."
        else:
            reply = stdout if stdout else "Befehl erfolgreich ausgeführt (keine Ausgabe)."
            
        return {
            "ok": ok,
            "reply": reply,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "reply": f"Timeout nach {timeout}s überschritten.", "returncode": -1}
    except Exception as e:
        return {"ok": False, "reply": f"Interner Fehler bei Ausführung: {str(e)}", "returncode": -1}


# apply lightweight wrapper to this module's callables
try:
    from app.tools.wrapper import validated_tool

    shell_command = validated_tool("powershell.shell_command", None)(shell_command)
except Exception:
    pass
