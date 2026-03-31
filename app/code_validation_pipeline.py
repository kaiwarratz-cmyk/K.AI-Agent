"""
Code Validation Pipeline – LLM Syntax Self-Repair mit Multi-Retry.

Best-Practice: 3-stufiger Feedback-Loop:
  1. ast.parse / PS-Parser für genaue Fehlerdiagnose
  2. LLM-Fix-Prompt mit Zeile+Spalte+Kontext-Ausschnitt
  3. Bis zu MAX_RETRIES Versuche, dann abbruch mit Fehlerliste

Verwendung:
    from app.code_validation_pipeline import validate_and_fix
    ok, fixed, errors = validate_and_fix(code, "python", cfg)
"""

from __future__ import annotations

import ast
import contextlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Top-Level-Import damit patch("app.code_validation_pipeline.LLMRouter") funktioniert
try:
    from app.llm_router import LLMRouter  # type: ignore[import]
except ImportError:
    LLMRouter = None  # type: ignore[assignment,misc]

MAX_RETRIES = 3  # Konsens aus Literatur: 3 ist optimal (SynCode, smolagents, InspectCoder)

# ---------------------------------------------------------------------------
# Code-Extraktion aus LLM-Output  (robuster als eine einzelne Regex)
# ---------------------------------------------------------------------------

_FENCE_PATTERNS = [
    # bevorzugte Sprache zuerst
    r"```(?:python|py)\s*\n?([\s\S]*?)```",
    r"```(?:powershell|pwsh|ps1)\s*\n?([\s\S]*?)```",
    # generische Blöcke
    r"```[a-z]*\s*\n?([\s\S]*?)```",
    r"`{3}([\s\S]+?)`{3}",
]


def extract_code_block(text: str, language: str = "python") -> str:
    """
    Extrahiert Code-Block aus LLM-Antwort.
    Probiert zuerst sprach-spezifische Fences, dann generische, dann Raw-Text.
    """
    text = text.strip()
    if not text:
        return ""

    # Versuche sprach-spezifischen Fence zuerst
    lang_aliases = {
        "python": ["python", "py"],
        "powershell": ["powershell", "pwsh", "ps1"],
    }
    aliases = lang_aliases.get(language.lower(), [language.lower()])
    for alias in aliases:
        pattern = rf"```(?:{alias})\s*\n?([\s\S]*?)```"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            code = m.group(1).strip()
            if code:
                return code

    # Generische Fences als Fallback
    generic = re.findall(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n?([\s\S]*?)```", text, re.IGNORECASE)
    if generic:
        # Nehme den längsten Block (wahrscheinlichster vollständiger Code)
        return max(generic, key=len).strip()

    # Inline-Backtick-Blöcke (selten aber möglich)
    inline = re.findall(r"`([^`]+)`", text)
    if inline:
        largest = max(inline, key=len)
        if len(largest) > 30:
            return largest.strip()

    # Kein Fence → Bereinige offensichtliche Erklärungsteile
    cut_markers = ["\n**erklärung", "\n**erklaerung", "\n**wie man", "\n**wichtige", "\n###", "\nhier ist", "\ndieser code"]
    lower = text.lower()
    cut_pos = len(text)
    for marker in cut_markers:
        i = lower.find(marker)
        if i > 0:
            cut_pos = min(cut_pos, i)
    return text[:cut_pos].strip()


# ---------------------------------------------------------------------------
# Syntax-Diagnose (Python + PowerShell)
# ---------------------------------------------------------------------------


def _check_python_syntax(code: str) -> Optional[str]:
    """Gibt None zurück wenn OK, sonst detaillierte Fehlermeldung mit Kontext-Zeilen."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        lineno = getattr(exc, "lineno", None)
        col = getattr(exc, "offset", None)
        msg = getattr(exc, "msg", str(exc))
        # Kontext: 2 Zeilen um den Fehler herum
        lines = code.splitlines()
        ctx_lines: List[str] = []
        if lineno:
            start = max(0, lineno - 3)
            end = min(len(lines), lineno + 2)
            for i, line in enumerate(lines[start:end], start=start + 1):
                marker = ">>>" if i == lineno else "   "
                ctx_lines.append(f"{marker} {i:4d}: {line}")
        ctx = "\n".join(ctx_lines)
        col_info = f", Spalte {col}" if col else ""
        return f"SyntaxError Zeile {lineno}{col_info}: {msg}\n{ctx}"


def _check_powershell_syntax(code: str) -> Optional[str]:
    """Gibt None zurück wenn OK, sonst Fehlermeldung vom PS-Parser."""
    tmp: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = Path(f.name)
        safe = str(tmp).replace("'", "''")
        ps_cmd = (
            "$tokens=$null; $errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{safe}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors -and $errors.Count -gt 0) { "
            "$errors | Select-Object -First 3 | ForEach-Object { "
            "Write-Output ($_.Message + ' @ Zeile ' + $_.Extent.StartLineNumber) "
            "}; exit 1 }"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        if proc.returncode != 0:
            return (proc.stdout or proc.stderr or "PS-Parser meldet Fehler.").strip()
        return None
    except subprocess.TimeoutExpired:
        return "PowerShell-Parser Timeout"
    except FileNotFoundError:
        return None  # PS nicht verfügbar → überspringen
    finally:
        if tmp is not None:
            with contextlib.suppress(Exception):
                tmp.unlink(missing_ok=True)


def check_syntax(code: str, language: str) -> Optional[str]:
    """Öffentliche Syntax-Prüfung. Gibt None (OK) oder Fehlerbeschreibung zurück."""
    lang = language.strip().lower()
    if lang == "python":
        return _check_python_syntax(code)
    if lang in {"powershell", "pwsh", "ps1"}:
        return _check_powershell_syntax(code)
    return None  # unbekannte Sprache → nicht blockieren


# ---------------------------------------------------------------------------
# Fix-Prompt Builder
# ---------------------------------------------------------------------------

_PYTHON_FIX_TEMPLATE = """\
Ein Python-Script hat nach automatischer Bereinigung noch einen Syntaxfehler.
Behebe NUR diesen Syntaxfehler. Antworte AUSSCHLIESSLICH mit dem korrigierten Python-Code.
KEIN Erklärungs-Text, KEINE Markdown-Blöcke, KEIN Präambel.

VERBOTEN im Code:
- `from app.` oder `import app.`
- Funktionen die mit `_handle_` oder `_llm_` beginnen
- Nur Standard-Bibliotheken und gängige PyPI-Pakete

FEHLER (Versuch {attempt}/{max_retries}):
{error}

CODE:
{code}
"""

_POWERSHELL_FIX_TEMPLATE = """\
Ein PowerShell-Script hat einen Syntaxfehler.
Behebe NUR diesen Syntaxfehler. Antworte AUSSCHLIESSLICH mit dem korrigierten PowerShell-Code.
KEIN Erklärungs-Text, KEINE Markdown-Blöcke.

FEHLER (Versuch {attempt}/{max_retries}):
{error}

CODE:
{code}
"""


def _build_fix_prompt(language: str, error: str, code: str, attempt: int, max_retries: int) -> str:
    tmpl = _PYTHON_FIX_TEMPLATE if language == "python" else _POWERSHELL_FIX_TEMPLATE
    # Code auf 6000 Zeichen kürzen, aber mit Fehlerstelle vollständig
    truncated = code[:6000] + ("\n# [ABGESCHNITTEN]" if len(code) > 6000 else "")
    return tmpl.format(
        error=error[:800],
        code=truncated,
        attempt=attempt,
        max_retries=max_retries,
    )


# ---------------------------------------------------------------------------
# Haupt-API
# ---------------------------------------------------------------------------


def validate_and_fix(
    code: str,
    language: str,
    cfg: Dict[str, Any],
    max_retries: int = MAX_RETRIES,
    context: str = "",
) -> Tuple[bool, str, List[str]]:
    """
    Validiert und repariert Code via Self-Repair-Loop.

    Args:
        code:        Der zu prüfende Code-String.
        language:    "python" oder "powershell".
        cfg:         Agent-Config (für LLMRouter).
        max_retries: Maximale LLM-Repair-Versuche (Standard: 3).
        context:     Optionaler Kontext-String für Debugging.

    Returns:
        (ok, fixed_code, error_log)
        ok=True  → Code ist syntaktisch korrekt (ggf. nach Fix).
        ok=False → Auch nach max_retries kein valider Code.
        error_log: Liste aller aufgetretenen Fehler pro Versuch.
    """
    if not code.strip():
        return False, code, ["Leerer Code-String"]

    lang = language.strip().lower()
    if lang not in {"python", "powershell", "pwsh", "ps1"}:
        # Unbekannte Sprache → nicht blockieren, als OK durchlassen
        return True, code, []

    error_log: List[str] = []

    # Initiale Prüfung
    error = check_syntax(code, lang)
    if error is None:
        return True, code, []

    # Self-Repair Loop
    current_code = code
    for attempt in range(1, max_retries + 1):
        error_log.append(f"Versuch {attempt}: {error}")

        fix_prompt = _build_fix_prompt(lang, error, current_code, attempt, max_retries)
        try:
            if LLMRouter is None:
                error_log.append(f"Versuch {attempt}: LLMRouter nicht verfügbar")
                break
            router = LLMRouter(cfg)
            raw = router.chat(prompt=fix_prompt)
            raw_text = str(raw.text if hasattr(raw, "text") else raw)
        except Exception as exc:
            error_log.append(f"LLM-Fehler bei Versuch {attempt}: {exc}")
            break

        candidate = extract_code_block(raw_text, language=lang)
        if not candidate.strip():
            error_log.append(f"Versuch {attempt}: LLM lieferte keinen Code")
            continue

        new_error = check_syntax(candidate, lang)
        if new_error is None:
            return True, candidate, error_log

        # LLM hat neuen Syntaxfehler eingebaut → mit neuem Fehler weiter
        error = new_error
        current_code = candidate

    error_log.append(f"Aufgegeben nach {max_retries} Versuchen.")
    return False, current_code, error_log
