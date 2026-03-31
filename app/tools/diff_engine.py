import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.tools.filesystem import _safe_abspath

def fs_apply_patch(path: str, patch_text: str) -> Dict[str, Any]:
    """
    Wendet einen Unified Diff (patch) auf eine Datei an.
    Bietet gegenüber fs_edit_replace folgende Vorteile:
    1. Multi-Point Edits: Mehrere Änderungen in einem Durchgang.
    2. Kontext-Aware: Nutzt Umgebungszeilen zur Verifizierung.
    3. Standard-Format: Kompatibel mit git diff/patch.
    """
    path = _safe_abspath(path)
    p = Path(path)
    
    if not p.exists():
        return {"ok": False, "error": f"Datei {path} nicht gefunden."}
    
    try:
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        
        # Patch parsen und anwenden
        patched_lines = _apply_unified_diff(lines, patch_text)
        
        # Backup erstellen
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = p.with_suffix(p.suffix + f".bak_{ts}_diff")
        shutil.copy2(p, backup)
        
        # Schreiben
        p.write_text("".join(patched_lines), encoding="utf-8")
        
        return {
            "ok": True, 
            "message": f"SUCCESS: Patch erfolgreich auf {path} angewendet.",
            "backup": backup.name
        }
    except Exception as e:
        return {"ok": False, "error": f"Patch-Fehler: {str(e)}"}

def _apply_unified_diff(original_lines: List[str], patch_text: str) -> List[str]:
    """Interne Logik zur Verarbeitung von Unified Diff Chunks."""
    patch_lines = patch_text.splitlines(keepends=True)
    result_lines = list(original_lines)
    
    # Header überspringen (--- / +++)
    i = 0
    while i < len(patch_lines) and (patch_lines[i].startswith("---") or patch_lines[i].startswith("+++")):
        i += 1
        
    chunks = []
    current_chunk = []
    
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [line]
        elif current_chunk:
            current_chunk.append(line)
        i += 1
    if current_chunk:
        chunks.append(current_chunk)
        
    # Chunks von hinten nach vorn anwenden, um Indizes nicht zu korrumpieren
    # Da wir aber Zeilen-Matching machen, ist die Reihenfolge wichtig.
    # Wir nutzen ein Offset-Tracking.
    
    offset = 0
    for chunk in chunks:
        header = chunk[0]
        # Format: @@ -start,len +start,len @@
        m = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", header)
        if not m:
            continue
            
        old_start = int(m.group(1)) - 1 # 0-indexed
        old_len = int(m.group(2) or 1)
        
        new_start = old_start + offset
        
        # Context-Verifizierung
        expected_context = []
        replacement = []
        for l in chunk[1:]:
            if l.startswith(" "):
                expected_context.append(l[1:])
                replacement.append(l[1:])
            elif l.startswith("-"):
                expected_context.append(l[1:])
            elif l.startswith("+"):
                replacement.append(l[1:])
        
        # Prüfen ob original an dieser Stelle passt (oder fuzzy suchen)
        # Für den ersten Wurf: Exaktes Matching am Ziel-Ort
        actual_context = result_lines[new_start : new_start + old_len]
        
        # Whitespace-tolerant comparison
        def _norm(ls): return [l.strip() for l in ls]
        
        if _norm(actual_context) != _norm(expected_context):
            # Fuzzy Search im Bereich von +/- 20 Zeilen
            found = False
            for shift in range(-20, 21):
                check_pos = new_start + shift
                if check_pos < 0 or check_pos + old_len > len(result_lines): continue
                if _norm(result_lines[check_pos : check_pos + old_len]) == _norm(expected_context):
                    new_start = check_pos
                    found = True
                    break
            if not found:
                raise ValueError(f"Chunk-Kontext passt nicht an Zeile {old_start+1} (+/- 20 Zeilen Fuzzy).")
        
        # Ersetzung durchführen
        result_lines[new_start : new_start + old_len] = replacement
        
        # Offset für nächste Chunks anpassen
        new_len = len(replacement)
        offset += (new_len - old_len)
        
    return result_lines
