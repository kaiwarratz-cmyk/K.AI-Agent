from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def list_printers() -> List[Dict[str, str]]:
    """
    Listet alle verfügbaren Drucker auf (Windows).
    
    Returns:
        Liste von Dicts mit 'name', 'status', 'is_default'
    """
    try:
        # PowerShell-Befehl um Drucker aufzulisten
        cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-Printer | Select-Object Name, PrinterStatus, @{Name='IsDefault';Expression={$_.Name -eq (Get-WmiObject -Query 'SELECT * FROM Win32_Printer WHERE Default=True').Name}} | ConvertTo-Json"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return []
        
        import json
        printers_data = json.loads(result.stdout)
        
        # Wenn nur ein Drucker, ist es ein Dict statt Liste
        if isinstance(printers_data, dict):
            printers_data = [printers_data]
        
        printers = []
        for p in printers_data:
            printers.append({
                "name": str(p.get("Name", "")),
                "status": str(p.get("PrinterStatus", "Unknown")),
                "is_default": bool(p.get("IsDefault", False)),
            })
        
        return printers
    except Exception as exc:
        raise RuntimeError(f"Fehler beim Auflisten der Drucker: {exc}")


def print_file(
    file_path: str,
    printer_name: Optional[str] = None,
    copies: int = 1,
) -> Dict[str, Any]:
    """
    Druckt eine Datei auf einem Windows-Drucker.
    
    Args:
        file_path: Pfad zur Datei (PDF, Bild, Dokument)
        printer_name: Name des Druckers (None = Standarddrucker)
        copies: Anzahl der Kopien
    
    Returns:
        Dict mit 'success', 'printer', 'file', 'copies'
    """
    file = Path(file_path)
    
    if not file.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")
    
    if not file.is_file():
        raise ValueError(f"Kein gültiger Dateipfad: {file_path}")
    
    copies = max(1, int(copies))
    
    # Wenn kein Drucker angegeben, nutze Standarddrucker
    if not printer_name:
        printers = list_printers()
        default = next((p for p in printers if p["is_default"]), None)
        if not default:
            raise RuntimeError("Kein Standarddrucker gefunden")
        printer_name = default["name"]

    
    # PowerShell-Befehl zum Drucken
    # Nutze Start-Process mit -Verb Print für universelles Drucken
    ps_script = f"""
$printer = '{printer_name}'
$file = '{str(file.resolve())}'
$copies = {copies}

# Prüfe ob Drucker existiert
$printerExists = Get-Printer -Name $printer -ErrorAction SilentlyContinue
if (-not $printerExists) {{
    Write-Error "Drucker nicht gefunden: $printer"
    exit 1
}}

# Drucke die Datei
for ($i = 1; $i -le $copies; $i++) {{
    Start-Process -FilePath $file -Verb Print -WindowStyle Hidden -Wait
}}

Write-Output "Gedruckt: $file auf $printer ($copies Kopien)"
"""
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unbekannter Fehler"
            raise RuntimeError(f"Druckfehler: {error_msg}")
        
        return {
            "success": True,
            "printer": printer_name,
            "file": str(file.resolve()),
            "copies": copies,
            "message": result.stdout.strip(),
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("Druckvorgang hat zu lange gedauert (Timeout)")
    except Exception as exc:
        raise RuntimeError(f"Fehler beim Drucken: {exc}")


# Wrap with validation decorator
try:
    from app.tools.wrapper import validated_tool
    list_printers = validated_tool("list_printers", None)(list_printers)
    print_file = validated_tool("print_file", None)(print_file)
except Exception:
    pass
