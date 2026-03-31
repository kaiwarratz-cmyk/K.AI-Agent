from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Set


@dataclass
class ReasoningSignals:
    is_question: bool
    is_approval_reply: bool
    explicit_tool_intent: bool
    mixed_answer_save_intent: bool
    internal_memory_query: bool


def _has_any(text: str, words: List[str]) -> bool:
    return any(w in text for w in words)


# --- Signal Groups 2026 ----------------------------------------------------
_FILESYSTEM_KEYWORDS = {
    "schreibe datei", "schreibe json", "json datei", "haenge an datei", 
    "anhaenge an datei", "lies datei", "zeige dateien", "liste dateien", 
    "zeige ordner", "liste ordner", "list folders", "list dirs", "show folders", 
    "show dirs", "kopier", "verschieb", "loesch", "benenne", "rename", 
    "erstelle ordner", "touch datei", "leere datei", "touch file"
}

_CODE_KEYWORDS = {
    "python:", "powershell:", "pwsh:", "```python", "```powershell", "```pwsh"
}

_TOOL_VERBS = r"\b(zeige\w*|zeig\w*|liste\w*|list\w*|lies\w*|lese\w*|read\w*|schreibe\w*|write\w*|kopier\w*|copy\w*|verschieb\w*|move\w*|loesch\w*|lösch\w*|delete\w*|rename\w*|umbenenn\w*|erstelle\w*|create\w*|nutze\w*|mkdir|touch)\b"
_TOOL_OBJECTS = r"\b(datei|dateien|file|files|ordner|verzeichnis|folder|dir|pfad|path|json|txt|skript|script)\b"


def detect_signals(message: str) -> ReasoningSignals:
    text = (message or "").strip()
    lower = text.lower()
    is_question = ("?" in lower) or bool(
        re.match(r"^(wer|was|wann|wo|warum|wieso|wie|hast|which|what|when|where|why|how)\b", lower)
    )
    
    # Check explicit intents
    explicit_tool_intent = any(kw in lower for kw in _FILESYSTEM_KEYWORDS) or \
                          any(kw in lower for kw in _CODE_KEYWORDS)

    if not explicit_tool_intent:
        tool_verb = bool(re.search(_TOOL_VERBS, lower))
        tool_object = bool(re.search(_TOOL_OBJECTS, lower))
        path_hint = bool(re.search(r"([a-z]:\\|[a-z]:(?:\s|$)|data/workspace|[/\\])", lower))
        explicit_tool_intent = tool_verb and (tool_object or path_hint)

    if not explicit_tool_intent:
        # Screenshot detection
        screenshot_action = bool(
            re.search(
                r"\b(mach\w*|mache\w*|erstelle\w*|create\w*|take\w*|capture\w*)\b.*\b(screenshot|bildschirmfoto|screen\s*shot)\b",
                lower,
            )
        )
        explicit_tool_intent = screenshot_action

    mixed_answer_save_intent = _has_any(
        lower,
        ["speicher", "speichere", "save", "als textdatei", "as text file", "in eine textdatei", "textdatei", ".txt"],
    ) and (not explicit_tool_intent)

    internal_memory_query = bool(
        re.search(
            r"(was\s+(wei[sß]t|weisst|wei.t|merkst)\s+du\s+(ueber|über|u.ber|.ber)\s+mich|hast\s+du\s+dir\s+.*gemerkt|was\s+hatten\s+wir\s+zu)",
            lower,
        )
    )

    return ReasoningSignals(
        is_question=is_question,
        is_approval_reply=False,
        explicit_tool_intent=explicit_tool_intent,
        mixed_answer_save_intent=mixed_answer_save_intent,
        internal_memory_query=internal_memory_query,
    )


def build_plan(signals: ReasoningSignals) -> List[str]:
    steps: List[str] = ["help", "memory_commands", "clear_context", "personal_facts", "self_improve"]
    if signals.explicit_tool_intent:
        steps.extend(["script_memory", "script_create", "script_exec", "filesystem"])
    elif signals.mixed_answer_save_intent:
        steps.append("answer_and_save")
    
    if signals.internal_memory_query:
        steps.append("memory_only_qa")
        
    steps.extend(["knowledge_or_web", "llm"])
    return steps


def reply_looks_like_internal_plan(reply: str) -> bool:
    lower = (reply or "").lower()
    indicators = [
        "anfrage einordnen", "umsetzung:", "verifikation:", "die anfrage ist mehrdeutig",
        "gemäß der regel", "gemaess der regel", "ich wähle die plausibelste option",
        "ich werde nun", "ich erstelle ein", "schritt 1:"
    ]
    return any(ind in lower for ind in indicators)


def sanitize_user_facing_reply(reply: str) -> str:
    """Removes agent's internal reasoning blocks from the final output."""
    text = (reply or "").strip()
    if not text or not reply_looks_like_internal_plan(text):
        return text

    # Anchors for the actual start of an answer
    anchors = ["hier ist", "hier sind", "antwort:", "**zutaten:**", "so geht's", "ergebnis:", "fertig:"]
    lower = text.lower()
    
    for anchor in anchors:
        pos = lower.find(anchor)
        if pos >= 0:
            candidate = text[pos + len(anchor):].strip().lstrip(":")
            if candidate: return candidate

    # Fallback: Filter by lines
    drop_patterns = [
        r"^(\*\*)?(anfrage einordnen|umsetzung|verifikation|ergebnis|ziel):(\*\*)?.*$",
        r"^die anfrage ist mehrdeutig.*$",
        r"^gem[aä][ßs] der regel.*$",
        r"^ich werde.*$",
        r"^darf ich.*$",
        r"^bevor ich.*$",
    ]
    
    kept = []
    for line in text.splitlines():
        if not any(re.match(p, line.strip(), re.IGNORECASE) for p in drop_patterns):
            kept.append(line)
            
    return "\n".join(kept).strip()
