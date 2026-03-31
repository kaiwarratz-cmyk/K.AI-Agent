from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.reasoning import ReasoningSignals, build_plan, detect_signals


@dataclass
class TaskState:
    message_original: str
    message_working: str
    source: str
    dialog_key: str
    signals: Optional[ReasoningSignals] = None
    interpretation: Optional[Dict[str, Any]] = None
    steps: List[str] = field(default_factory=list)
    factual_domain: str = ""
    needs_verification: bool = False


def build_task_state(
    *,
    message: str,
    source: str,
    dialog_key: str,
    augment_followup: Callable[[str], str],
    llm_interpret: Callable[[str, ReasoningSignals], Optional[Dict[str, Any]]],
    apply_interpretation: Callable[[str, ReasoningSignals, Dict[str, Any]], Tuple[str, ReasoningSignals]],
    promote_tool_intent: Callable[[str, ReasoningSignals], ReasoningSignals],
    detect_factual_domain: Callable[[str], str],
    needs_verification: Callable[[str], bool],
) -> TaskState:
    working = augment_followup(message)
    signals = detect_signals(working)
    interpretation = llm_interpret(working, signals)
    if isinstance(interpretation, dict):
        working, signals = apply_interpretation(working, signals, interpretation)
    signals = promote_tool_intent(working, signals)
    steps = build_plan(signals)
    factual_domain = detect_factual_domain(working)
    verify = bool(factual_domain) or needs_verification(working)
    return TaskState(
        message_original=message,
        message_working=working,
        source=source,
        dialog_key=dialog_key,
        signals=signals,
        interpretation=interpretation if isinstance(interpretation, dict) else None,
        steps=steps,
        factual_domain=factual_domain,
        needs_verification=verify,
    )

