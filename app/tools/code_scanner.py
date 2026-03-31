import os
import ast
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.tools.filesystem import _safe_abspath

def fs_code_outline(path: str) -> str:
    """
    Erstellt eine strukturelle Uebersicht einer Code-Datei (Signaturen von Klassen/Funktionen).
    Ideal um Architektur zu verstehen ohne die ganze Datei zu lesen (Context-schonend).
    Unterstuetzt aktuell: .py (via AST). Fallback fuer andere Sprachen: Einfaches Line-Listing.
    """
    path = _safe_abspath(path)
    p = Path(path)
    
    if not p.exists():
        return f"ERROR: Datei {path} nicht gefunden."
    
    if p.suffix == ".py":
        return _outline_python(p)
    else:
        # Fallback: Extrahiere Zeilen mit 'class' oder 'def' oder 'function'
        return _outline_generic(p)

def fs_search_symbol(name: str, path: str = ".") -> str:
    """
    Sucht nach einer Symboldefinition (Klasse/Funktion) im angegebenen Pfad.
    """
    root = _safe_abspath(path)
    hits = []
    
    for r, _, files in os.walk(root):
        if any(x in r.lower() for x in {".git", "__pycache__", ".venv"}): continue
        for f in files:
            if f.endswith(".py"):
                full_path = os.path.join(r, f)
                try:
                    tree = ast.parse(Path(full_path).read_text(encoding="utf-8", errors="ignore"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            if node.name == name:
                                hits.append(f"{full_path} - Line {node.lineno}: {type(node).__name__} {node.name}")
                except Exception:
                    continue
    
    return "\n".join(hits) if hits else f"Kein Symbol '{name}' gefunden."

def fs_find_usages(symbol: str, path: str = ".") -> str:
    """
    Sucht alle Stellen (Referenzen) im Projekt, an denen ein Symbol verwendet wird.
    Hilft dabei, Seiteneffekte bei Aenderungen zu erkennen (Refactoring-Check).
    """
    root = _safe_abspath(path)
    hits = []
    
    # Text-basierter Pre-Scanner (schnell)
    for r, _, files in os.walk(root):
        if any(x in r.lower() for x in {".git", "__pycache__", ".venv"}): continue
        for f in files:
            full_p = Path(r) / f
            # Pruefe ob wir in dieser Datei suchen wollen (Text-Endungen)
            if f.endswith(('.py', '.js', '.ts', '.html', '.css', '.md', '.json')):
                try:
                    content = full_p.read_text(encoding="utf-8", errors="ignore")
                    if symbol in content:
                        # Detaillierte Prüfung fuer Python: Ignoriere (meist) Kommentare/Strings
                        if f.endswith(".py"):
                            file_hits = _find_usages_python(full_p, symbol)
                            hits.extend(file_hits)
                        else:
                            # Generic: Einfacher Zeilenscan
                            for idx, line in enumerate(content.splitlines(), 1):
                                if symbol in line:
                                    hits.append(f"{full_p} (L{idx}): {line.strip()}")
                except Exception:
                    continue
                    
    return "\n".join(hits) if hits else f"Keine Verwendungen fuer '{symbol}' gefunden."

def _find_usages_python(p: Path, symbol: str) -> List[str]:
    hits = []
    try:
        content = p.read_text(encoding="utf-8")
        tree = ast.parse(content)
        # Wir suchen nach Name-Nodes (Referenzen) oder Attributen
        for node in ast.walk(tree):
            line_hit = None
            if isinstance(node, ast.Name) and node.id == symbol:
                line_hit = node.lineno
            elif isinstance(node, ast.Attribute) and node.attr == symbol:
                line_hit = node.lineno
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol:
                # Das ist die Definition selbst - zaehlt auch als "Usage/Def"
                line_hit = node.lineno
                
            if line_hit:
                # Zeile aus dem Content extrahieren fuer Vorschau
                line_text = content.splitlines()[line_hit-1].strip()
                hit_str = f"{p} (L{line_hit}): {line_text}"
                if hit_str not in hits: # Duplikate vermeiden (wenn mehrere Nodes in einer Zeile)
                    hits.append(hit_str)
    except:
        pass
    return hits

def _outline_python(p: Path) -> str:
    try:
        content = p.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = []
        lines.append(f"Outline fuer: {p.name}")
        
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                lines.append(f"[IMPORT] {ast.unparse(node)}")
            elif isinstance(node, ast.ClassDef):
                lines.append(f"CLASS {node.name} (Line {node.lineno})")
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Extrahiere Argumente
                        args = [a.arg for a in sub.args.args]
                        lines.append(f"  └── METHOD {sub.name}({', '.join(args)}) (Line {sub.lineno})")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                lines.append(f"DEF {node.name}({', '.join(args)}) (Line {node.lineno})")
                
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR beim Parsen von {p.name}: {str(e)}"

def _outline_generic(p: Path) -> str:
    # Einfacher Zeilen-Scanner für gängige Keywords
    keywords = {"class ", "function ", "def ", "pub fn ", "export const "}
    lines = []
    lines.append(f"Outline (Generic) fuer: {p.name}")
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, 1):
                clean = line.strip()
                if any(clean.startswith(kw) for kw in keywords):
                    lines.append(f"L{idx}: {clean}")
    except Exception as e:
        return f"ERROR beim Lesen von {p.name}: {str(e)}"
    return "\n".join(lines) if len(lines) > 1 else f"Keine Signaturen in {p.name} gefunden."
