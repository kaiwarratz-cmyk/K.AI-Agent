from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.tools.filesystem import list_entries, read_file, write_file


def _has_any(msg: str, words: list[str]) -> bool:
    return any(w in msg for w in words)


def _normalize_raw_path(raw: str) -> str:
    text = str(raw or "").strip().strip("'\"")
    if not text:
        return ""
    return text.replace("/", "\\")


def _extract_unc_path(message: str) -> Optional[str]:
    quoted = re.findall(r'"([^"]+)"', message)
    for q in quoted:
        qn = _normalize_raw_path(q)
        if qn.startswith("\\\\"):
            return qn
    raw = str(message or "")
    idx = raw.find("\\\\")
    if idx < 0:
        return None
    tail = raw[idx:].strip()
    for marker in [" als laufwerk", " unter laufwerk", " mit laufwerk", " auf laufwerk", " bitte", " und "]:
        cut = tail.lower().find(marker)
        if cut >= 0:
            tail = tail[:cut].strip()
            break
    return _normalize_raw_path(tail)


def _extract_path(message: str) -> Optional[str]:
    quoted = re.findall(r'"([^"]+)"', message)
    if quoted:
        return _normalize_raw_path(quoted[0])
    windows_path = re.search(r"(?<![A-Za-z])([A-Za-z]:(?!//)(?:\\[^\s\"]*)?)(?!/)", message)
    if windows_path:
        return _normalize_raw_path(windows_path.group(1))
    unc = _extract_unc_path(message)
    if unc:
        return _normalize_raw_path(unc)
    bare_file = re.search(
        r"\b([A-Za-z0-9_\-\.]+\.(?:txt|md|json|log|csv|yaml|yml|xml|ini|cfg|py|ps1|bat))\b",
        message,
    )
    if bare_file:
        return _normalize_raw_path(str(bare_file.group(1) or ""))
    rel = re.search(r"\b(?:in|unter|at|inside)\b\s+([.\w:\\/\-]+)", message, flags=re.IGNORECASE)
    if rel:
        cand = _normalize_raw_path(rel.group(1))
        low = str(cand or "").strip().lower()
        if low in {"workspace", "verzeichnis", "ordner", "directory", "folder"}:
            return None
        return cand
    return None


def _extract_list_file_extension(msg: str) -> Optional[str]:
    m = re.search(r"\.([a-z0-9]{1,8})\b", msg, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b([a-z0-9]{2,6})\s*(?:datei|dateien|files?)\b", msg, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def _resolve_path(raw_path: Optional[str], root_dir: Path) -> Path:
    if not raw_path:
        return root_dir
    text = _normalize_raw_path(raw_path)
    if text.startswith("\\\\"):
        return Path(text)
    if re.match(r"^[A-Za-z]:\\", text):
        return Path(text)
    if text.startswith(".\\") or text.startswith("..\\"):
        return (root_dir / text).resolve()
    return (root_dir / text).resolve()


def decompose_compound_steps(message: str) -> list[dict]:
    # Compound steps are handled by the LLM (MCP/Scripts). Keep deterministic fallback disabled.
    return []


def analyze_filesystem_request(message: str, cfg: Dict[str, Any], root_dir: Path) -> Dict[str, Any]:
    msg = str(message or "")
    low = msg.lower()

    # --- read file ---
    if _has_any(low, ["lies", "lese", "read file", "datei lesen", "zeige datei", "öffne datei"]):
        raw_path = _extract_path(msg)
        if not raw_path:
            return {"handled": True, "tool": "fs_read_file", "reply": "Bitte Dateipfad angeben."}
        target = _resolve_path(raw_path, root_dir)
        return {
            "handled": True,
            "tool": "fs_read_file",
            "action": {"kind": "read_file", "path": str(target)},
            "note": f"Datei lesen: {target}",
        }

    # --- write file ---
    if _has_any(low, ["schreib", "write", "speicher", "save"]):
        raw_path = _extract_path(msg)
        if raw_path:
            target = _resolve_path(raw_path, root_dir)
            split_match = re.split(r"\b(?:in|unter|to)\b", msg, maxsplit=1, flags=re.IGNORECASE)
            content_raw = ""
            if split_match:
                content_raw = str(split_match[0] or "")
            content_raw = re.sub(r"^\s*(schreibe|schreib|write|speicher|save)\s*", "", content_raw, flags=re.IGNORECASE).strip()
            content = _normalize_raw_path(content_raw) if content_raw.startswith(("'", '"')) else content_raw
            if not content:
                return {"handled": True, "tool": "fs_write_file", "reply": "Bitte den Inhalt angeben."}
            return {
                "handled": True,
                "tool": "fs_write_file",
                "admin_required": True,
                "action": {"kind": "write_file", "path": str(target), "content": content},
                "note": f"Datei schreiben: {target}",
            }

    # --- list entries ---
    # Keep fallback narrow: only explicit list phrasing, no broad regex intent routing.
    list_intent = _has_any(
        low,
        [
            "auflisten",
            "liste ",
            "liste:",
            "list files",
            "list dirs",
            "list entries",
            "zeige dateien",
            "zeige ordner",
            "zeige verzeichnisse",
            "show files",
            "show folders",
            "show directories",
        ],
    )
    if list_intent:
        raw_path = _extract_path(msg)
        target = _resolve_path(raw_path, root_dir)
        want = "all"
        if _has_any(low, ["ordner", "dirs", "verzeichnisse", "directories", "folder"]):
            want = "dirs"
        if _has_any(low, ["datei", "dateien", "files", "file"]):
            want = "files" if want != "dirs" else "all"
        recursive = _has_any(low, ["rekursiv", "recursive", "unterordner", "inkl. unterordner"])
        ext_filter = _extract_list_file_extension(low)
        max_items = 500 if recursive else 200
        action = {
            "kind": "list_entries",
            "path": str(target),
            "want": want,
            "recursive": recursive,
            "ext": ext_filter,
            "max_items": max_items,
        }
        return {
            "handled": True,
            "tool": "fs_list_entries",
            "admin_required": True,
            "action": action,
            "note": f"Eintraege listen: {target}",
        }

    return {"handled": False}


def execute_filesystem_action(action: Dict[str, Any]) -> Tuple[str, str]:
    kind = str(action.get("kind", ""))
    if kind == "read_file":
        path = str(action["path"])
        content = read_file(path)
        if len(content) > 16000:
            content = content[:16000] + "\n... (gekuerzt)"
        return "fs_read_file", f"{path}\n\n{content}"

    def _unc_server_root(path_text: str) -> Optional[str]:
        p = str(path_text or "").strip()
        if not p.startswith("\\\\"):
            return None
        parts = [x for x in p.split("\\") if x]
        if len(parts) == 1:
            return parts[0]
        return None

    if kind == "list_entries":
        path = str(action["path"])
        server_root = _unc_server_root(path)
        if server_root:
            try:
                result = subprocess.run(
                    ["net", "view", f"\\\\{server_root}"],
                    capture_output=True,
                    text=True,
                    encoding="cp850",
                    errors="replace",
                    timeout=10,
                )
                if result.returncode == 0:
                    lines = result.stdout.splitlines()
                    shares = []
                    in_share_section = False
                    # Detect column position of "Typ" from header line
                    typ_col = None
                    for line in lines:
                        if "---" in line:
                            in_share_section = True
                            continue
                        if not in_share_section:
                            # Find the header line to detect column positions
                            low = line.lower()
                            if "typ" in low or "type" in low:
                                typ_col = low.index("typ") if "typ" in low else low.index("type")
                            continue
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        if any(x in line_stripped for x in [
                            "Der Befehl wurde", "The command", "erfolgreich", "successfully",
                            "completed", "ausgeführt"
                        ]):
                            continue
                        # Extract share name using Typ column position (fixed-width)
                        if typ_col and len(line) > typ_col:
                            share_name = line[:typ_col].strip()
                        else:
                            # Fallback: strip known type words from end
                            parts = line_stripped.split(None, 1)
                            share_name = parts[0] if parts else line_stripped
                            for type_word in ["Platte", "Drucker", "Disk", "Print", "IPC"]:
                                if share_name.endswith(f" {type_word}"):
                                    share_name = share_name[: -len(type_word) - 1].strip()
                        if share_name:
                            shares.append(f"\\\\{server_root}\\{share_name}")
                    if shares:
                        return "fs_list_entries", f"Freigaben auf \\\\{server_root} ({len(shares)} gefunden):\n" + "\n".join(shares)
                    return "fs_list_entries", f"Keine Freigaben auf \\\\{server_root} gefunden oder keine Berechtigung."
                return "fs_list_entries", f"Konnte \\\\{server_root} nicht erreichen. Ist der Server erreichbar?"
            except Exception as exc:
                return "fs_list_entries", f"Fehler beim Auflisten von \\\\{server_root}: {exc}"

        want = str(action.get("want", "all") or "all")
        recursive = bool(action.get("recursive", False))
        ext = str(action.get("ext")) if action.get("ext") else None
        max_items = int(action.get("max_items", 200) or 200)
        items = list_entries(path, want=want, recursive=recursive, ext=ext, max_items=max_items)
        preview = items[:25]
        suffix = "" if len(items) <= len(preview) else f"\n... und {len(items) - len(preview)} weitere."
        if want == "dirs":
            head = f"Ordner unter {path} ({len(items)} gefunden)"
            empty = "(keine Ordner gefunden)"
            tool = "fs_list_dirs"
        elif want == "all":
            head = f"Dateien und Unterverzeichnisse unter {path} ({len(items)} gefunden)"
            empty = "(keine Eintraege gefunden)"
            tool = "fs_list_entries"
        else:
            head = f"Dateien unter {path} ({len(items)} gefunden)"
            empty = "(keine Dateien gefunden)"
            tool = "fs_list_files"
        body = "\n".join(preview) if preview else empty
        return tool, f"{head}\n{body}{suffix}"

    if kind == "write_file":
        return "fs_write_file", write_file(str(action["path"]), str(action.get("content", "")))

    return "fs_unknown", f"Nicht unterstuetzte FS-Aktion: {kind}"
