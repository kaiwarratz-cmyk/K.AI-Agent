from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional

def _extract_any_path(text: str) -> Optional[str]:
    """Extrahiert einen moeglichen Dateipfad aus einem Freitext."""
    if not text: return None
    # Suche nach Windows-Pfaden (C:\...) oder UNC (\\...) oder relativen Pfaden mit Extension
    m = re.search(r'([a-zA-Z]:\\[^:;*?"<>|\n\r]+|\\[\\[a-zA-Z0-9._-]+\\[^:;*?"<>|\n\r]+|[a-zA-Z0-9._/-]+\.[a-zA-Z0-9]{2,10})', text)
    if m:
        p = m.group(1).strip().rstrip(".")
        if len(p) > 2: return p
    return None

def _has_any(text: str, markers: List[str]) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)
