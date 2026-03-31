from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import List, Optional
import app.tool_engine as tool_engine

try:
    from send2trash import send2trash
except Exception:  # pragma: no cover - optional dependency
    send2trash = None  # type: ignore[assignment]


def list_entries(
    path: str,
    want: str = "files",
    recursive: bool = True,
    ext: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[str]:
    path = os.path.expandvars(path)
    p = Path(path)
    if not p.exists():
        return []
    ext_norm = None
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        ext_norm = ext_norm.lower()
    try:
        iterator = p.rglob("*") if recursive else p.iterdir()
        result: list[str] = []
        want_norm = str(want or "files").strip().lower()
        if want_norm not in {"files", "dirs", "all"}:
            want_norm = "files"
        
        # We need to catch errors during iteration as well (e.g. System Volume Information)
        try:
            for entry in iterator:
                try:
                    if want_norm in {"files", "all"} and entry.is_file():
                        if ext_norm and entry.suffix.lower() != ext_norm:
                            continue
                        result.append(str(entry))
                        if max_items is not None and len(result) >= max_items:
                            break
                    elif want_norm in {"dirs", "all"} and entry.is_dir():
                        result.append(str(entry))
                        if max_items is not None and len(result) >= max_items:
                            break
                except (PermissionError, OSError) as exc:
                    tool_engine.tool_store.log("filesystem_list_entry_error", f"Error accessing entry {entry}: {exc}")
                    continue
        except (PermissionError, OSError) as exc:
            # If the iterator itself fails (e.g. iterdir() on protected dir)
            tool_engine.tool_store.log("filesystem_list_iterator_error", f"Error creating or iterating {path}: {exc}")
            return []
            
        return result
    except Exception as exc:
        tool_engine.tool_store.log("filesystem_list_generic_error", f"Generic error in list_entries for {path}: {exc}")
        # If path exists but listing failed, return the error message for debugging
        if p.exists():
            return [f"ERROR_LIST_ENTRIES: {exc}"]
        return []


def count_entries(
    path: str,
    want: str = "files",
    recursive: bool = True,
    ext: Optional[str] = None,
) -> int:
    path = os.path.expandvars(path)
    p = Path(path)
    if not p.exists():
        return 0
    ext_norm = None
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        ext_norm = ext_norm.lower()
    iterator = p.rglob("*") if recursive else p.iterdir()
    total = 0
    want_norm = str(want or "files").strip().lower()
    if want_norm not in {"files", "dirs", "all"}:
        want_norm = "files"
    for entry in iterator:
        if want_norm in {"files", "all"}:
            if not entry.is_file():
                if want_norm != "all":
                    continue
            else:
                if ext_norm and entry.suffix.lower() != ext_norm:
                    continue
                total += 1
                continue
        if want_norm in {"dirs", "all"} and entry.is_dir():
            total += 1
    return total


def export_entries_to_file(
    path: str,
    out_path: str,
    want: str = "files",
    recursive: bool = True,
    ext: Optional[str] = None,
) -> str:
    path = os.path.expandvars(path)
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Quellpfad nicht gefunden: {src}")
    ext_norm = None
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        ext_norm = ext_norm.lower()
    dst = Path(out_path)
    
    # Prüfe ob Zielverzeichnis existiert, bevor mkdir aufgerufen wird
    if not dst.parent.exists():
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            raise FileNotFoundError(f"Zielverzeichnis kann nicht erstellt werden: {dst.parent} ({e})")
    
    iterator = src.rglob("*") if recursive else src.iterdir()
    count = 0
    with dst.open("w", encoding="utf-8") as fh:
        for entry in iterator:
            if want == "files":
                if not entry.is_file():
                    continue
                if ext_norm and entry.suffix.lower() != ext_norm:
                    continue
            elif want == "dirs":
                if not entry.is_dir():
                    continue
            else:
                continue
            fh.write(str(entry) + "\n")
            count += 1
    return f"Datei geschrieben: {dst} ({count} Eintraege)"


def read_file(path: str) -> str:
    path = _safe_abspath(path)  # AUTO-HEALING für UNC-Pfade!
    p = Path(path)
    raw = p.read_bytes()
    # Binär-Erkennung: wenn >30% der ersten 512 Bytes nicht-druckbar → Binärdatei
    sample = raw[:512]
    non_printable = sum(1 for b in sample if b < 9 or (14 <= b < 32) or b == 127)
    if sample and non_printable / len(sample) > 0.30:
        return (
            f"BINARY FILE: {p.name} ({len(raw)} Bytes) – kann nicht als Text gelesen werden.\n"
            f"Dateityp erkannt anhand Byte-Muster. Nutze sys_shell_command für Binär-Tools."
        )
    # Encoding-Fallback: utf-8 → cp1252 → latin-1 (latin-1 schlägt nie fehl)
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("latin-1", errors="replace")


def write_file(path: str, content: str) -> str:
    path = _safe_abspath(path)  # AUTO-HEALING für UNC-Pfade!
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Datei geschrieben: {p} ({len(content)} Zeichen)"


def append_file(path: str, content: str) -> str:
    path = os.path.expandvars(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"Datei erweitert: {p} (+{len(content)} Zeichen)"


def write_json_file(path: str, json_text: str) -> str:
    path = os.path.expandvars(path)
    parsed = json.loads(json_text)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"JSON-Datei geschrieben: {p}"


def touch_file(path: str) -> str:
    path = os.path.expandvars(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)
    return f"Datei erstellt/beruehrt: {p}"


def make_dir(path: str) -> str:
    path = os.path.expandvars(path)
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return f"Ordner erstellt: {p}"


def copy_path(src: str, dst: str) -> str:
    src = os.path.expandvars(src)
    dst = os.path.expandvars(dst)
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(f"Quelle nicht gefunden: {src_path}")
    if src_path.is_dir():
        if dst_path.exists() and dst_path.is_file():
            raise ValueError("Ziel ist eine Datei, Quelle ist ein Ordner.")
        shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        return f"Ordner kopiert: {src_path} -> {dst_path}"
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    return f"Datei kopiert: {src_path} -> {dst_path}"


def move_path(src: str, dst: str) -> str:
    src = os.path.expandvars(src)
    dst = os.path.expandvars(dst)
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(f"Quelle nicht gefunden: {src_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_path), str(dst_path))
    return f"Verschoben: {src_path} -> {dst_path}"


def rename_path(src: str, dst: str) -> str:
    return move_path(src, dst)


def delete_path(path: str, use_trash: bool = True) -> str:
    path = os.path.expandvars(path)
    p = Path(path)
    if not p.exists():
        return f"Nichts geloescht, nicht gefunden: {p}"
    if use_trash:
        if send2trash is not None:
            send2trash(str(p))
            kind = "Ordner" if p.is_dir() else "Datei"
            return f"{kind} in Papierkorb verschoben: {p}"
        # fallback if optional dependency is not installed
        use_trash = False
    if p.is_dir():
        shutil.rmtree(p)
        return f"Ordner geloescht: {p}"
    p.unlink(missing_ok=True)
    return f"Datei geloescht: {p}"


def bulk_delete_ext(folder: str, ext: str, recursive: bool, use_trash: bool = True) -> str:
    folder = os.path.expandvars(folder)
    f = Path(folder)
    if not f.exists() or not f.is_dir():
        raise FileNotFoundError(f"Ordner nicht gefunden: {f}")
    normalized_ext = ext if ext.startswith(".") else f".{ext}"
    iterator = f.rglob(f"*{normalized_ext}") if recursive else f.glob(f"*{normalized_ext}")
    deleted = 0
    moved_to_trash = False
    fallback_permanent = False
    for file_path in iterator:
        if file_path.is_file():
            if use_trash and send2trash is not None:
                send2trash(str(file_path))
                moved_to_trash = True
            else:
                if use_trash and send2trash is None:
                    fallback_permanent = True
                file_path.unlink(missing_ok=True)
            deleted += 1
    if moved_to_trash:
        msg = f"{deleted} Datei(en) mit Endung {normalized_ext} in Papierkorb verschoben unter {f}"
        if fallback_permanent:
            msg += " (teilweise permanent, send2trash nicht verfuegbar)"
        return msg
    msg = f"{deleted} Datei(en) mit Endung {normalized_ext} geloescht unter {f}"
    if fallback_permanent:
        msg += " (send2trash nicht verfuegbar)"
    return msg


def copy_all_files(src_dir: str, dst_dir: str, ext: Optional[str], recursive: bool) -> str:
    src_dir = os.path.expandvars(src_dir)
    dst_dir = os.path.expandvars(dst_dir)
    src = Path(src_dir).resolve()
    dst = Path(dst_dir).resolve()
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Quellordner nicht gefunden: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        pattern = f"*{ext_norm}"
    else:
        pattern = "*"
    iterator = src.rglob(pattern) if recursive else src.glob(pattern)
    copied = 0
    for file_path in iterator:
        if not file_path.is_file():
            continue
        # Zielverzeichnis nicht in sich selbst kopieren
        try:
            file_path.relative_to(dst)
            continue
        except ValueError:
            pass
        rel = file_path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        copied += 1
    return f"{copied} Datei(en) kopiert: {src} -> {dst}"


def move_all_files(src_dir: str, dst_dir: str, ext: Optional[str], recursive: bool) -> str:
    src_dir = os.path.expandvars(src_dir)
    dst_dir = os.path.expandvars(dst_dir)
    src = Path(src_dir).resolve()
    dst = Path(dst_dir).resolve()
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Quellordner nicht gefunden: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        pattern = f"*{ext_norm}"
    else:
        pattern = "*"
    iterator = list(src.rglob(pattern) if recursive else src.glob(pattern))
    moved = 0
    for file_path in iterator:
        if not file_path.is_file():
            continue
        # Zielverzeichnis nicht in sich selbst verschieben
        try:
            file_path.relative_to(dst)
            continue
        except ValueError:
            pass
        rel = file_path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(target))
        moved += 1
    return f"{moved} Datei(en) verschoben: {src} -> {dst}"


def create_zip_archive(src_path: str, archive_path: str, recursive: bool = True) -> str:
    src_path = os.path.expandvars(src_path)
    archive_path = os.path.expandvars(archive_path)
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Quelle nicht gefunden: {src}")
    dst = Path(archive_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(dst, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_file():
            zf.write(src, arcname=src.name)
            count = 1
        else:
            it = src.rglob("*") if recursive else src.glob("*")
            for p in it:
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(src)))
                    count += 1
    return f"Archiv erstellt: {dst} ({count} Datei(en))"


def extract_zip_archive(archive_path: str, target_dir: str) -> str:
    archive_path = os.path.expandvars(archive_path)
    target_dir = os.path.expandvars(target_dir)
    arc = Path(archive_path)
    if not arc.exists() or not arc.is_file():
        raise FileNotFoundError(f"Archiv nicht gefunden: {arc}")
    dst = Path(target_dir)
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(arc, mode="r") as zf:
        members = zf.namelist()
        zf.extractall(dst)
    return f"Archiv entpackt: {arc} -> {dst} ({len(members)} Eintraege)"


def search_in_files(
    path: str,
    pattern: str,
    recursive: bool = True,
    ext: Optional[str] = None,
    case_sensitive: bool = False,
    max_hits: int = 200,
) -> str:
    path = os.path.expandvars(path)
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Pfad nicht gefunden: {root}")
    ext_norm = None
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        ext_norm = ext_norm.lower()
    files = [root] if root.is_file() else list(root.rglob("*") if recursive else root.glob("*"))
    needle = pattern if case_sensitive else pattern.lower()
    hits: list[str] = []
    for p in files:
        if not p.is_file():
            continue
        if ext_norm and p.suffix.lower() != ext_norm:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = txt.splitlines()
        for idx, line in enumerate(lines, start=1):
            hay = line if case_sensitive else line.lower()
            if needle in hay:
                hits.append(f"{p}:{idx}: {line[:220]}")
                if len(hits) >= max_hits:
                    body = "\n".join(hits)
                    return f"Treffer ({len(hits)}+, begrenzt):\n{body}"
    if not hits:
        return "Keine Treffer gefunden."
    body = "\n".join(hits)
    return f"Treffer ({len(hits)}):\n{body}"


def _sha256_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_duplicate_files(path: str, recursive: bool = True, ext: Optional[str] = None, max_groups: int = 120) -> str:
    path = os.path.expandvars(path)
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Pfad nicht gefunden: {root}")
    ext_norm = None
    if ext:
        ext_norm = ext if ext.startswith(".") else f".{ext}"
        ext_norm = ext_norm.lower()
    it = [root] if root.is_file() else list(root.rglob("*") if recursive else root.glob("*"))
    by_size: dict[int, list[Path]] = {}
    for p in it:
        if not p.is_file():
            continue
        if ext_norm and p.suffix.lower() != ext_norm:
            continue
        try:
            sz = p.stat().st_size
        except Exception:
            continue
        by_size.setdefault(sz, []).append(p)
    groups: list[list[Path]] = []
    for _, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        by_hash: dict[str, list[Path]] = {}
        for p in candidates:
            try:
                hx = _sha256_of_file(p)
            except Exception:
                continue
            by_hash.setdefault(hx, []).append(p)
        for _, dup in by_hash.items():
                if len(dup) >= 2:
                    groups.append(dup)
                if len(groups) >= max_groups:
                    break
        if len(groups) >= max_groups:
            break
    if not groups:
        return "Keine Duplikate gefunden."
    lines: list[str] = []
    total_files = 0
    for i, g in enumerate(groups, start=1):
        lines.append(f"[Gruppe {i}]")
        for p in g:
            lines.append(str(p))
            total_files += 1
    return f"Duplikat-Gruppen: {len(groups)}, Dateien in Gruppen: {total_files}\n" + "\n".join(lines)


def copy_file_chunked(src: str, dst: str, chunk_size_mb: int = 8, resume: bool = True) -> str:
    src = os.path.expandvars(src)
    dst = os.path.expandvars(dst)
    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists() or not src_p.is_file():
        raise FileNotFoundError(f"Quelle nicht gefunden: {src_p}")
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    chunk = max(1, int(chunk_size_mb)) * 1024 * 1024
    offset = 0
    mode = "wb"
    if resume and dst_p.exists():
        offset = dst_p.stat().st_size
        mode = "ab"
    copied = 0
    with src_p.open("rb") as fin, dst_p.open(mode) as fout:
        if offset > 0:
            fin.seek(offset)
        while True:
            buf = fin.read(chunk)
            if not buf:
                break
            fout.write(buf)
            copied += len(buf)
    total = src_p.stat().st_size
    ok = dst_p.exists() and dst_p.stat().st_size == total
    return f"Chunk-Kopie: {src_p} -> {dst_p}, bytes_neu={copied}, total={total}, komplett={ok}"


def watch_path(path: str, duration_sec: int = 15, interval_sec: float = 1.0) -> str:
    path = os.path.expandvars(path)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Pfad nicht gefunden: {p}")
    duration = max(1, min(int(duration_sec), 300))
    interval = max(0.2, min(float(interval_sec), 10.0))
    start = time.time()
    changes: list[str] = []
    known: dict[str, float] = {}
    def snapshot() -> dict[str, float]:
        out: dict[str, float] = {}
        it = [p] if p.is_file() else p.rglob("*")
        for e in it:
            try:
                if e.is_file():
                    out[str(e)] = e.stat().st_mtime
            except Exception:
                continue
        return out
    known = snapshot()
    while time.time() - start < duration:
        time.sleep(interval)
        cur = snapshot()
        prev_keys = set(known.keys())
        cur_keys = set(cur.keys())
        for added in sorted(cur_keys - prev_keys):
            changes.append(f"+ {added}")
        for removed in sorted(prev_keys - cur_keys):
            changes.append(f"- {removed}")
        for common in sorted(prev_keys.intersection(cur_keys)):
            if cur[common] != known[common]:
                changes.append(f"~ {common}")
        known = cur
    if not changes:
        return f"Watch abgeschlossen ({duration}s): keine Aenderungen."
    preview = "\n".join(changes[:200])
    suffix = "" if len(changes) <= 200 else f"\n... und {len(changes)-200} weitere."
    return f"Watch abgeschlossen ({duration}s), Aenderungen: {len(changes)}\n{preview}{suffix}"

import os
import fnmatch


def _safe_abspath(p: str) -> str:
    """
    UNC-sicheres os.path.abspath() mit AUTO-HEALING.
    • Heilt Pfade wie /Medianas → \\Medianas (LLM-Fehler)
    • Heilt Forward-Slashes → Backslashes
    • Behandelt beide UNC-Format: \\\\server und //server
    • Heilt LLM over-escaping: \\\\\\\\server → \\server (>2 Backslashes → exakt 2)
    """
    import re as _re
    p = os.path.expandvars(p)
    # Normalisiere Forward-Slashes zu Backslashes (//server → \\server)
    p = p.replace("/", "\\")

    # LLM over-escaping fix: 3+ führende Backslashes → exakt 2 (UNC-Standard)
    if _re.match(r"^\\{3,}", p):
        p = "\\\\" + p.lstrip("\\")
    # AUTO-HEALING: /Medianas/... oder \Medianas\... → \\Medianas\...
    elif p.startswith("\\") and not p.startswith("\\\\"):
        # Prüfe ob es wie ein UNC-Pfad aussieht (hat einen Server-Namen am Anfang)
        first_part = p.lstrip("\\").split("\\")[0]
        # Wenn es kein Laufwerk ist (z.B. nicht "C"), behandle es als UNC-Server
        if first_part and len(first_part) > 1 and ":" not in first_part:
            p = "\\\\" + p.lstrip("\\")

    if p.startswith("\\\\"):
        return os.path.normpath(p)
    # Absolute Pfade unverändert zurückgeben
    if os.path.isabs(p):
        return os.path.abspath(p)
    # Relative Pfade: zur Workspace-Basis auflösen statt zu CWD.
    # Verhindert dass 'datei.bat' im K.AI-Root landet statt in data/workspace/.
    try:
        from pathlib import Path as _Path
        from app.config import ROOT_DIR as _ROOT
        workspace = _ROOT / "data" / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        # Strip redundant workspace-prefix the LLM sometimes adds (e.g. "data/workspace/file.txt")
        try:
            p_rel = _Path(p).relative_to(_Path("data") / "workspace")
        except ValueError:
            p_rel = _Path(p)
        return str((workspace / p_rel).resolve())
    except Exception:
        return os.path.abspath(p)


def fs_read_file(path: str) -> str:
    path = os.path.expandvars(path)
    """Alias for read_file."""
    return read_file(path)

def fs_write_file(path: str, content: str) -> str:
    """Alias for write_file."""
    path = _safe_abspath(path)  # AUTO-HEALING
    return write_file(path, content)

def fs_grep(path: str, pattern: str, recursive: bool = True) -> str:
    """Durchsucht TEXT-Dateiinhalte nach einem Regex-Muster (Zeile für Zeile).
    NUR für Text-Dateien geeignet – sucht NICHT nach Dateinamen und NICHT in Binärdateien (MP3, FLAC, Video etc.).
    Für Dateinamen-Suche: fs_find_files verwenden.
    Unterstützt mehrere Muster (Semikolon-getrennt)."""
    import re
    import os
    root = _safe_abspath(path)

    if not os.path.exists(root):
        return f"ERROR: Path {path} not found."
    
    # Split patterns
    patterns = [p.strip() for p in pattern.replace(",", ";").split(";") if p.strip()]
    if not patterns: return "ERROR: No pattern provided."
    
    results = []
    try:
        regexes = [re.compile(p, re.IGNORECASE) for p in patterns]
        if recursive:
            for r, dirs, files in os.walk(root):
                for f in files:
                    full_path = os.path.join(r, f)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                            for line_num, line in enumerate(fh, 1):
                                if any(reg.search(line) for reg in regexes):
                                    results.append(f"{full_path}:{line_num}: {line.strip()}")
                    except Exception: continue
        else:
            for f in os.listdir(root):
                full_path = os.path.join(root, f)
                if os.path.isfile(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                            for line_num, line in enumerate(fh, 1):
                                if any(reg.search(line) for reg in regexes):
                                    results.append(f"{full_path}:{line_num}: {line.strip()}")
                    except Exception: continue
        return "\n".join(results) if results else "No matches found."
    except Exception as e:
        return f"ERROR during grep: {e}"

def fs_find_files(path: str, pattern: str = "*", recursive: bool = True) -> str:
    """High-performance file search supporting multiple patterns (semicolon separated).
    Gibt ALLE Treffer ohne Limit zurück. Große Ergebnisse werden vom Dispatcher
    automatisch in eine Datei gespeichert (statt den LLM-Context zu fluten).
    Sucht nach DATEINAMEN (nicht nach Dateiinhalten – dafür fs_grep verwenden).
    """
    import os
    import fnmatch
    root = _safe_abspath(path)
    if not os.path.exists(root):
        return f"ERROR: Path {path} does not exist."

    # Split patterns by ; or ,
    patterns = [p.strip().lower() for p in pattern.replace(",", ";").split(";") if p.strip()]
    if not patterns: patterns = ["*"]

    # Process each pattern
    search_patterns = []
    for p in patterns:
        if "*" not in p and "?" not in p:
            search_patterns.append(f"*{p}*")
        else:
            search_patterns.append(p)

    results = []
    access_errors: list[str] = []
    skip_dirs = {"$recycle.bin", "system volume information", ".git", "__pycache__"}

    def _onerror(exc: OSError) -> None:
        """Collect inaccessible directories instead of silently skipping them."""
        access_errors.append(str(exc.filename or exc))

    try:
        if recursive:
            for r, dirs, files in os.walk(root, onerror=_onerror):
                dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
                for name in files:
                    name_lower = name.lower()
                    if any(fnmatch.fnmatch(name_lower, sp) for sp in search_patterns):
                        results.append(os.path.join(r, name))
        else:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_file():
                        name_lower = entry.name.lower()
                        if any(fnmatch.fnmatch(name_lower, sp) for sp in search_patterns):
                            results.append(entry.path)
    except Exception as e:
        return f"ERROR during thorough search: {e}"

    # Build warning block for inaccessible directories
    warning = ""
    if access_errors:
        shown = access_errors[:20]
        extra = f" (+{len(access_errors) - 20} weitere)" if len(access_errors) > 20 else ""
        warning = (
            f"\nWARNUNG: {len(access_errors)} Verzeichnis(se) nicht zugänglich (Zugriff verweigert){extra}:\n"
            + "\n".join(f"  - {e}" for e in shown)
            + "\nHinweis: Benutze sys_python_exec mit os.walk() und expliziter Fehlerbehandlung "
            "für NAS-Pfade mit eingeschränkten Berechtigungen."
        )

    if not results:
        return (
            f"❌ Found 0 files matching '{pattern}' in {path}.{warning}\n"
            f"\n"
            f"⚠️  WICHTIG: Das bedeutet WAHRSCHEINLICH der Pfad ist FALSCH!\n"
            f"    Nicht das Pattern, sondern der PFAD ist das Problem!\n"
            f"\n"
            f"Nutze fs_list_dir('{path}') um zu überprüfen, ob der Pfad existiert!\n"
            f"Wenn nicht: Falscher Pfad, mit mem_update_plan neu planen!"
        )
    return f"Found {len(results)} files:\n" + "\n".join(results) + warning

def fs_list_dir(path: str) -> str:
    """Fast directory listing using os.scandir."""
    path = _safe_abspath(path)  # AUTO-HEALING für UNC-Pfade!
    p = Path(path)
    if not p.exists():
        return f"ERROR: Path {path} does not exist."
    try:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
                type_str = "DIR " if entry.is_dir() else "FILE"
                entries.append(f"[{type_str}] {entry.name}")
        return "\n".join(sorted(entries))
    except Exception as e:
        return f"ERROR listing directory: {e}"

def fs_get_tree(path: str, max_depth: int = 2, indent: str = "") -> str:
    """High-performance directory tree generation using os.scandir.

    🚨 DEFAULT max_depth=2 (nicht 3!) um massive Output-Dateien zu vermeiden.
    """
    import os
    path = _safe_abspath(path)  # AUTO-HEALING
    if max_depth < 0: return ""

    # 🚨 SAFETY: Wenn indent sehr lang ist (tiefe Recursion), abbrechne
    if len(indent) > 100:
        return f"{indent}└── [DEPTH LIMIT ERREICHT - zu tiefe Rekursion!]"

    try:
        if not os.path.exists(path):
            return f"ERROR: Path {path} does not exist."

        output = []
        try:
            with os.scandir(path) as it:
                entries = sorted(list(it), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception as e:
            if indent == "": # Root level error
                return f"ERROR accessing {path}: {e}"
            return f"{indent}└── [Zugriff verweigert]"

        # 🚨 SAFETY: Limit Anzahl Einträge pro Verzeichnis (verhindert 10000+ Dateien-Listing)
        if len(entries) > 500:
            entries = entries[:500]
            output.append(f"{indent}📦 [LISTE GEKÜRZT: 500 von {len(entries)} Einträgen]")

        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            output.append(f"{indent}{connector}{entry.name}")

            if entry.is_dir() and max_depth > 0:
                new_indent = indent + ("    " if is_last else "│   ")
                subtree = fs_get_tree(entry.path, max_depth - 1, new_indent)
                if subtree and not subtree.startswith("ERROR"):
                    output.append(subtree)

        return "\n".join(output) if output else f"{indent}└── (leer)"
    except Exception as e:
        return f"ERROR during tree generation: {e}"

def fs_edit_replace(path: str, old_str: str, new_string: str) -> str:
    """Surgically replaces a string in a file. Includes safety checks and backup."""
    path = _safe_abspath(path)  # AUTO-HEALING
    p = Path(path)
    if not p.exists():
        return f"ERROR: File {path} not found."
    
    try:
        content = p.read_text(encoding="utf-8")
        if old_str not in content:
            return f"ERROR: The string to replace was not found in {path}. Make sure the 'old_str' matches EXACTLY (including whitespace)."
        
        count = content.count(old_str)
        if count > 1:
            return f"ERROR: Ambiguous replacement. Found {count} occurrences of the string. Provide more context in 'old_str'."
            
        new_content = content.replace(old_str, new_string)
        
        # Create backup
        backup_path = p.with_suffix(p.suffix + ".bak")
        shutil.copy(p, backup_path)
        
        p.write_text(new_content, encoding="utf-8")
        return f"SUCCESS: Replaced 1 occurrence in {path}. Backup created at {backup_path.name}."
    except Exception as e:
        return f"ERROR during edit: {e}"


# fs_ tool aliases for auto-dispatch
fs_delete = delete_path
fs_move = move_path
fs_copy = copy_path
fs_rename = rename_path
def fs_append(path: str, content: str) -> str:
    """Alias for append_file with path auto-healing (_safe_abspath)."""
    path = _safe_abspath(path)
    return append_file(path, content)
fs_mkdir = make_dir
fs_zip_create = create_zip_archive
fs_zip_extract = extract_zip_archive

# Wrap callables with a lightweight logging decorator from wrapper.py
try:  # pragma: no cover - best-effort wrapping
    from app.tools.wrapper import (
        validated_tool,
        ListEntriesModel,
        ReadFileModel,
        WriteFileModel,
        AppendFileModel,
        DeletePathModel,
        CopyMoveModel,
        CopyAllFilesModel,
        MoveAllFilesModel,
        BulkDeleteExtModel,
        CreateZipModel,
        ExtractZipModel,
        ExportEntriesModel,
    )

    # mapping of function name -> model
    _model_map = {
        "list_entries": ListEntriesModel,
        "read_file": ReadFileModel,
        "write_file": WriteFileModel,
        "append_file": AppendFileModel,
        "delete_path": DeletePathModel,
        "copy_path": CopyMoveModel,
        "move_path": CopyMoveModel,
        "rename_path": CopyMoveModel,
        "copy_all_files": CopyAllFilesModel,
        "move_all_files": MoveAllFilesModel,
        "bulk_delete_ext": BulkDeleteExtModel,
        "create_zip_archive": CreateZipModel,
        "extract_zip_archive": ExtractZipModel,
        "export_entries_to_file": ExportEntriesModel,
    }

    _wrapped = set()
    for _name, _model in _model_map.items():
        if _name in globals() and callable(globals().get(_name)):
            globals()[_name] = validated_tool(f"filesystem.{_name}", _model)(globals()[_name])
            _wrapped.add(_name)

    # fallback: wrap remaining callables without strict models
    for _n, _v in list(globals().items()):
        if _n in _wrapped:
            continue
        if callable(_v) and getattr(_v, "__module__", "").endswith("app.tools.filesystem"):
            globals()[_n] = validated_tool(f"filesystem.{_n}", None)(_v)
except Exception:
    pass