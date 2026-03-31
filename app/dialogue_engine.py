"""
Dialogue Engine for K.AI
========================
Complete state machine + intent routing + working memory + history compression.

Architecture:
- MemGPT/Letta: Working Memory (Core Memory) per dialog_key
- LangGraph: Explicit state machine, intent-based routing, fast path
- LangChain ConversationSummaryBuffer: Last 4 turns raw, older compressed
"""
from __future__ import annotations
import json
import threading
import time
from typing import Optional, Dict, Any, List, Callable


class DialogueState:
    IDLE = "idle"
    WORKING = "working"
    AWAITING_INPUT = "awaiting_input"
    DONE = "done"
    FAILED = "failed"


class Route:
    SIMPLE = "simple"          # Direct LLM answer, NO react loop
    FOLLOWUP = "followup"      # React loop with max_iterations=15, inject working memory
    INTERRUPT = "interrupt"    # Cancel current task, then handle as new_task
    NEW_TASK = "new_task"      # Full react loop max_iterations=50, clear working_notes


# Fix 8: Konstanten zentral in constants.py definiert – kein doppeltes Hardcoding.
from app.constants import MAX_WORKING_NOTES, KEEP_RAW_TURNS


def _is_short_reply(message: str, max_len: int = 15) -> bool:
    return len(message.strip()) <= max_len


class WorkingMemory:
    """
    MemGPT-inspired Core Memory wrapper around TaskStateManager.
    Per dialog_key structured memory that persists across turns.
    """
    def __init__(self, dialog_key: str):
        self.dialog_key = dialog_key
        self._tsm = None

    def _get_tsm(self):
        if self._tsm is None:
            from app.task_state import get_task_state_manager
            self._tsm = get_task_state_manager()
        return self._tsm

    def load(self) -> Dict[str, Any]:
        """Load full state. Returns empty dict if not found."""
        state = self._get_tsm().get_state(self.dialog_key)
        if state is None:
            return {
                "dialogue_state": DialogueState.IDLE,
                "task_desc": "",
                "working_notes": [],
                "pending_question": "",
                "history_summary": "",
            }
        # Parse working_notes JSON
        notes_raw = state.get("working_notes", "[]")
        try:
            notes = json.loads(notes_raw) if isinstance(notes_raw, str) else (notes_raw or [])
        except Exception:
            notes = []
        state["working_notes"] = notes if isinstance(notes, list) else []
        return state

    def set_task(self, task_desc: str) -> None:
        self._get_tsm().set_task(self.dialog_key, task_desc)
        self._get_tsm().set_dialogue_state(self.dialog_key, DialogueState.WORKING)

    def set_dialogue_state(self, state: str) -> None:
        self._get_tsm().set_dialogue_state(self.dialog_key, state)

    def add_note(self, note: str) -> None:
        self._get_tsm().add_working_note(self.dialog_key, note)

    def set_pending_question(self, question: str) -> None:
        self._get_tsm().set_pending_question(self.dialog_key, question)

    def clear_pending_question(self) -> None:
        self._get_tsm().set_pending_question(self.dialog_key, "")

    def complete(self, success: bool = True, final_reply: str = "") -> None:
        self._get_tsm().complete_task(self.dialog_key, success=success, final_reply=final_reply)
        new_state = DialogueState.DONE if success else DialogueState.FAILED
        self._get_tsm().set_dialogue_state(self.dialog_key, new_state)

    def clear(self) -> None:
        self._get_tsm().clear_task(self.dialog_key)

    def get_dialogue_state(self) -> str:
        state = self.load()
        return state.get("dialogue_state", DialogueState.IDLE)

    def get_working_notes(self) -> List[str]:
        return self.load().get("working_notes", [])

    def get_task_desc(self) -> str:
        state = self.load()
        return state.get("task_desc", "") or ""

    def set_history_summary(self, summary: str) -> None:
        self._get_tsm().set_history_summary(self.dialog_key, summary)

    def get_history_summary(self) -> str:
        state = self.load()
        return state.get("history_summary", "") or ""


class HistoryBuffer:
    """
    LangChain ConversationSummaryBuffer inspired.
    Last KEEP_RAW_TURNS turns stay raw.
    Older turns get compressed by LLM into a summary stored in WorkingMemory.
    """

    @staticmethod
    def compress_if_needed(
        dialog_key: str,
        history: List[Dict],
        working_mem: WorkingMemory,
        cfg: Optional[Dict] = None,
    ) -> None:
        """
        If history has more than KEEP_RAW_TURNS*2 items, compress the older half.
        Summary is stored in working_memory.history_summary.
        """
        if len(history) <= KEEP_RAW_TURNS * 2:
            return  # Nothing to compress yet

        old_turns = history[: len(history) - KEEP_RAW_TURNS * 2]
        if not old_turns:
            return

        # Build text to summarize
        lines = []
        for item in old_turns:
            role = "Nutzer" if item.get("role") == "user" else "K.AI"
            text = str(item.get("text", "")).strip()[:300]
            if text:
                lines.append(f"{role}: {text}")

        if not lines:
            return

        existing_summary = working_mem.get_history_summary()

        try:
            # Try to summarize with LLM
            if cfg is not None:
                from app.llm_router import LLMRouter
                router = LLMRouter(cfg)
                prompt_parts = []
                if existing_summary:
                    prompt_parts.append(f"Vorherige Zusammenfassung:\n{existing_summary}\n")
                prompt_parts.append("Neue ältere Gesprächsteile:\n" + "\n".join(lines))
                prompt_parts.append(
                    "\nErstelle eine kurze Zusammenfassung (max 3 Sätze) was bisher besprochen wurde. "
                    "Nur Fakten, keine Wertungen."
                )
                result = router.chat(prompt="\n".join(prompt_parts))
                summary_text = result.text if hasattr(result, "text") else str(result)
                if summary_text and len(summary_text) > 10:
                    working_mem.set_history_summary(summary_text[:800])
                    return
        except Exception:
            pass

        # Fallback: simple concatenation
        simple = " | ".join(lines[:5])
        if simple:
            working_mem.set_history_summary(simple[:400])


def _llm_route_message(
    message: str,
    working_mem: WorkingMemory,
    history: List[Dict],
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """LLM-based follow-up routing. Returns dict with route/needs_clarification/etc."""
    if not isinstance(cfg, dict):
        return None
    try:
        from app.llm_router import LLMRouter
        state = working_mem.load()
        current_task = str(state.get("task_desc", "") or "")[:300]
        dialogue_state = str(state.get("dialogue_state", DialogueState.IDLE) or "")
        pending_q = str(state.get("pending_question", "") or "")[:300]
        recent = history[-6:] if history else []
        recent_lines: List[str] = []
        for item in recent:
            role = "Nutzer" if item.get("role") == "user" else "K.AI"
            text = str(item.get("text", "") or "").strip()
            if text:
                recent_lines.append(f"{role}: {text[:300]}")
        # Context-aware hints for routing accuracy
        awaiting_hint = ""
        if dialogue_state == DialogueState.AWAITING_INPUT and pending_q:
            awaiting_hint = (
                f"\nWICHTIG: Der Agent wartet auf Nutzer-Antwort zur Frage: '{pending_q}'. "
                f"Die neue Nachricht ist SEHR WAHRSCHEINLICH eine Antwort darauf "
                f"→ route='followup', NICHT 'new_task'.\n"
            )
        done_hint = ""
        if dialogue_state in (DialogueState.DONE, DialogueState.FAILED):
            done_hint = (
                "\nHINWEIS: Vorheriger Task abgeschlossen. Korrekturen oder Ergänzungen "
                "zur letzten Antwort sind 'followup', nicht 'new_task'.\n"
            )
        prompt = (
            "Klassifiziere die neue Nachricht als route: simple|followup|new_task|interrupt.\n"
            "Antworte NUR als JSON nach Schema.\n\n"
            "SIMPLE (kurze Antwort, keine Aufgabe):\n"
            "- Personale Fragen: 'Wie geht es dir?', 'Was kannst du machen?', 'Wer bist du?'\n"
            "- Grüße & Bestätigungen: 'Hallo', 'Danke', 'Ok', 'Verstanden'\n"
            "- Status-Checks: 'Bist du noch da?', 'Läufts noch?'\n"
            "→ Antwort: 1-2 Sätze, direkt und kurz\n\n"
            "NEW_TASK (Aufgabe zur Ausführung):\n"
            "- Explizite Aufträge: 'Schreibe', 'Erstelle', 'Automatisiere'\n"
            "- Recherche-Aufgaben: 'gibt es eine banking api?', 'Finde heraus...'\n"
            "- Analyse-Aufträge: 'Analysiere', 'Debugge', 'Überprüfe'\n"
            "- Komplexe Fragen: 'Wie könnte ich...?', 'Entwickle einen Plan'\n"
            "→ Antwort: ReAct-Loop mit Recherche/Analyse/Implementierung\n\n"
            "FOLLOWUP: Bezieht sich klar auf aktuelle Aufgabe.\n"
            "INTERRUPT: 'Stop', 'Vergiss das' — nur wenn Task läuft.\n\n"
            f"{awaiting_hint}{done_hint}\n"
            f"Aktuelle Aufgabe: {current_task}\n"
            f"Dialogzustand: {dialogue_state}\n"
            f"Offene Frage: {pending_q}\n"
            "Letzte Nachrichten:\n" + ("\n".join(recent_lines) if recent_lines else "(keine)") + "\n\n"
            f"Neue Nachricht: {str(message or '')[:600]}"
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "route": {"type": "string", "enum": ["simple", "followup", "new_task", "interrupt"]},
                "confidence": {"type": "number"},
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": "string"},
            },
            "required": ["route", "confidence", "needs_clarification", "clarification_question"],
        }
        router = LLMRouter(cfg)
        obj = router.chat_json(prompt=prompt, schema_name="followup_router_v1", schema=schema)
        if not isinstance(obj, dict):
            return None
        route = str(obj.get("route", "") or "").strip().lower()
        if route not in {"simple", "followup", "new_task", "interrupt"}:
            return None
        try:
            conf = float(obj.get("confidence", 0.0) or 0.0)
        except Exception:
            conf = 0.0
        needs = bool(obj.get("needs_clarification", False))
        q = str(obj.get("clarification_question", "") or "").strip()[:220]
        if needs and not q:
            q = "Meinst du das vorherige Thema oder etwas Neues?"
        return {
            "route": route,
            "confidence": conf,
            "needs_clarification": needs,
            "clarification_question": q,
        }
    except Exception:
        return None


class IntentRouter:
    """
    LangGraph conditional edges inspired.
    Routes incoming messages to the correct handler based on:
    1. classify_message() result
    2. Current dialogue state
    3. Context heuristics
    """

    @staticmethod
    def route(
        message: str,
        working_mem: WorkingMemory,
        history: List[Dict],
        cfg: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Optional[str]]:
        from app.dialogue_engine import Route, DialogueState
        
        lower = (message or "").lower()
        current_task = working_mem.get_task_desc()
        dialogue_state = working_mem.get_dialogue_state()

        # FORCED FOLLOWUP: Wenn der Agent auf eine Nutzer-Antwort wartet (AWAITING_INPUT),
        # immer als followup routen — kein LLM-Aufruf nötig, kein Kontextverlust möglich.
        # Ausnahme: expliziter Abbruch-Intent ("abbruch", "cancel", "stop", "vergiss").
        if dialogue_state == DialogueState.AWAITING_INPUT:
            state = working_mem.load()
            pending_q = str(state.get("pending_question", "") or "").strip()
            if pending_q:
                _abort_words = {"abbruch", "cancel", "stop", "vergiss", "neu", "anderes", "egal"}
                if not any(w in lower for w in _abort_words):
                    return Route.FOLLOWUP, None

        # OPT-1: Aggressiver NEW_TASK Check nur wenn KEIN aktiver Task läuft.
        # Vorher: jede Nachricht mit "schreibe/erstelle" brach den Kontext.
        # Jetzt: LLM entscheidet bei laufenden Tasks (WORKING/AWAITING_INPUT).
        if dialogue_state == DialogueState.IDLE and not current_task:
            if "schreibe" in lower or "erstelle" in lower or "create" in lower:
                return Route.NEW_TASK, None

        # FIX 4c: "weiter" Intent-Erkennung (CRUCIAL für "weiter" nach Bot-Restart!)
        _weiter_keywords = {"weiter", "mach weiter", "continue", "go on", "resumieren", "weitermachen"}
        if any(kw in lower for kw in _weiter_keywords):
            # "weiter" means: continue with previous conversation
            # If history exists: FOLLOWUP (continue task)
            # If no history: treat as new task (nothing to continue)
            if history and len(history) > 1:
                return Route.FOLLOWUP, None
            # else: continue to normal routing (will likely be NEW_TASK)

        llm_choice = _llm_route_message(message, working_mem, history, cfg=cfg)
        if isinstance(llm_choice, dict):
            if bool(llm_choice.get("needs_clarification", False)):
                return Route.SIMPLE, str(llm_choice.get("clarification_question", "") or "").strip()
            route = str(llm_choice.get("route", "") or "").strip().lower()
            if route == "simple":
                return Route.SIMPLE, None
            if route == "interrupt":
                return Route.INTERRUPT, None
            if route == "followup":
                return Route.FOLLOWUP, None
            return Route.NEW_TASK, None

        # Fallback to NEW_TASK if LLM routing was inconclusive
        return Route.NEW_TASK, None


def _find_last_task_boundary(history: List[Dict], working_mem: "WorkingMemory") -> Optional[int]:
    """
    Findet den Index der letzten abgeschlossenen Task in der History.
    Nach Task-Abschluss (state=DONE) sollten neue Messages nicht mit alten Task-Messages vermischt werden.

    Der DialogueState DONE ist das einzige Signal — keine Keyword-Heuristik nötig.
    Gibt die letzte Assistant-Message zurück als Boundary-Punkt.

    Returns: Index der letzten Assistant-Message, oder None wenn state != DONE.
    """
    if not history or len(history) < 2:
        return None

    dialogue_state = working_mem.get_dialogue_state()
    if dialogue_state != DialogueState.DONE:
        return None

    # State=DONE ist das Signal — letzte Assistant-Message ist die Boundary
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "assistant":
            return i

    return None


def build_enriched_context(
    message: str,
    dialog_key: str,
    history: List[Dict],
    working_mem: WorkingMemory,
    route: str,
) -> str:
    """
    Build the final context string for the LLM.
    Includes: history_summary + working_notes + last 4 raw turns + current message.
    """
    from app.context_manager import _compress_assistant_message

    state = working_mem.load()
    is_new_task = route == Route.NEW_TASK

    lines: List[str] = []

    # 1. History summary (compressed older turns)
    summary = state.get("history_summary", "") or ""
    if summary:
        lines.append("[GESPRÄCHS-ZUSAMMENFASSUNG]")
        lines.append(summary)
        lines.append("")

    # 2. Working notes (key facts discovered during task)
    if not is_new_task:
        notes = state.get("working_notes", [])
        if isinstance(notes, str):
            try:
                notes = json.loads(notes)
            except Exception:
                notes = []
        if notes and isinstance(notes, list) and len(notes) > 0:
            lines.append("[ARBEITSNOTIZEN – was bereits gefunden/getan wurde]")
            for i, note in enumerate(notes[-MAX_WORKING_NOTES:], 1):
                lines.append(f"  {i}. {note}")
            lines.append("")

    # 3. Active task info
    task_desc = state.get("task_desc", "") or ""
    dialogue_state = state.get("dialogue_state", DialogueState.IDLE)
    if (
        not is_new_task
        and task_desc
        and dialogue_state in (DialogueState.WORKING, DialogueState.AWAITING_INPUT)
    ):
        lines.append(f"[AKTIVE AUFGABE] {task_desc}")
        if route == Route.FOLLOWUP:
            lines.append("→ KONTEXT: Dies ist eine Folgeanfrage. Führe die Aufgabe nahtlos fort.")
        lines.append("")

    # 4. Pending question
    pending_q = state.get("pending_question", "") or ""
    if pending_q and not is_new_task:
        lines.append(f"[OFFENE FRAGE AN NUTZER] {pending_q}")
        lines.append("")

    # 5. History turns (filtered) – for NEW_TASK use max 2 items to avoid
    #    old instructions leaking into the new task context.
    if route == Route.NEW_TASK:
        # Inject previous task summary for continuity reference
        try:
            from app.context_manager import ContextManager as _CM2
            _summary_path = _CM2().workspace / "prev_task_summary.md"
            if _summary_path.exists():
                _prev = _summary_path.read_text(encoding="utf-8")[:800]
                lines.append(f"[VORHERIGER TASK – nur zur Referenz, nicht wiederholen]\n{_prev}")
                lines.append("")
        except Exception:
            pass
        recent = history[-2:]  # Only last exchange (1 user + 1 assistant max)
        if recent:
            lines.append("[NEUE AUFGABE – frischer Start | letzter Kontext:]")
    else:
        recent = history[-(KEEP_RAW_TURNS * 2):]
        if recent:
            lines.append("Kontext aus laufender Messenger-Session (letzte Nachrichten):")
    if recent:
        for item in recent:
            role = item.get("role", "")
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            if role == "user":
                lines.append(f"Nutzer: {text[:400]}")
            else:
                compressed = _compress_assistant_message(text)
                lines.append(f"K.AI: {compressed}")
        lines.append("")

    if not lines:
        return message

    lines.append(f"Aktuelle Anfrage: {message}")
    return "\n".join(lines)


def process_request(
    message: str,
    dialog_key: str,
    history: List[Dict],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Main entry point called from _chat_reply (SCHRITT 0.5 replacement).

    Returns dict with:
    - route: str ('simple'/'followup'/'interrupt'/'new_task')
    - context: str (enriched context to replace the message)
    - max_iterations: int (15 for followup, 50 for new_task)
    - early_reply: Optional[str] (set for 'simple' route - skip react loop)
    - working_mem_updated: bool
    """
    result: Dict[str, Any] = {
        "route": Route.NEW_TASK,
        "context": message,
        "max_iterations": 50,
        "early_reply": None,
        "working_mem_updated": False,
    }

    try:
        working_mem = WorkingMemory(dialog_key)

        # Fix 5: Kompression asynchron – blockiert den Chat-Thread nicht mehr.
        # Die Methode schreibt das Summary direkt in die DB; kein Returnwert nötig.
        if len(history) > KEEP_RAW_TURNS * 2:
            _t = threading.Thread(
                target=HistoryBuffer.compress_if_needed,
                args=(dialog_key, history, working_mem, cfg),
                daemon=True,
                name=f"HistCompress-{dialog_key[:8]}",
            )
            _t.start()

        # Route the message
        route, clarification_q = IntentRouter.route(message, working_mem, history, cfg=cfg)
        if clarification_q:
            working_mem.set_pending_question(clarification_q)
            working_mem.set_dialogue_state(DialogueState.AWAITING_INPUT)
            result["route"] = Route.SIMPLE
            result["context"] = message
            result["max_iterations"] = 0
            result["early_reply"] = clarification_q
            return result

        result["route"] = route

        # Handle INTERRUPT: clear task state, then treat as new task
        effective_route = route
        if route == Route.INTERRUPT:
            working_mem.clear()
            # Fix: Auch den ContextManager (Plan/Facts) hart zurücksetzen
            try:
                from app.context_manager import ContextManager
                _ctx = ContextManager()
                _prev_plan = _ctx.read_plan() if _ctx.plan_file.exists() else ""
                _prev_facts = _ctx.read_facts()
                if _prev_plan or _prev_facts:
                    _facts_str = "\n".join(f"- {k}: {v}" for k, v in _prev_facts.items())
                    # Task-Beschreibung: aus plan.md ## Aufgabe-Abschnitt lesen (working_mem liefert meist leer)
                    _cur_task = str(working_mem.get_task_desc() or "")[:400]
                    if not _cur_task and _prev_plan:
                        import re as _re
                        _m = _re.search(r'##\s*Aufgabe\s*\n(.*?)(?:\n##|\Z)', _prev_plan, _re.DOTALL)
                        _cur_task = _m.group(1).strip()[:400] if _m else ""
                    _archive = f"# Letzter Task\n**Aufgabe:** {_cur_task}\n\n{_prev_plan[:600]}\n\n## Fakten\n{_facts_str[:400]}"
                    (_ctx.workspace / "prev_task_summary.md").write_text(_archive, encoding="utf-8")
                _ctx.clear_session_state()
            except Exception: pass
            effective_route = Route.NEW_TASK
            result["max_iterations"] = 50
        elif route == Route.NEW_TASK:
            # Bei einem neuen Thema (aber keinem harten Abbruch) ebenfalls
            # den Plan und die Fakten löschen, um Kontext-Verschmutzung zu vermeiden.
            try:
                from app.context_manager import ContextManager
                _ctx = ContextManager()
                _prev_plan = _ctx.read_plan() if _ctx.plan_file.exists() else ""
                _prev_facts = _ctx.read_facts()
                if _prev_plan or _prev_facts:
                    _facts_str = "\n".join(f"- {k}: {v}" for k, v in _prev_facts.items())
                    # Task-Beschreibung: aus plan.md ## Aufgabe-Abschnitt lesen (working_mem liefert meist leer)
                    _cur_task = str(working_mem.get_task_desc() or "")[:400]
                    if not _cur_task and _prev_plan:
                        import re as _re
                        _m = _re.search(r'##\s*Aufgabe\s*\n(.*?)(?:\n##|\Z)', _prev_plan, _re.DOTALL)
                        _cur_task = _m.group(1).strip()[:400] if _m else ""
                    _archive = f"# Letzter Task\n**Aufgabe:** {_cur_task}\n\n{_prev_plan[:600]}\n\n## Fakten\n{_facts_str[:400]}"
                    (_ctx.workspace / "prev_task_summary.md").write_text(_archive, encoding="utf-8")
                _ctx.clear_session_state()
            except Exception: pass
            result["max_iterations"] = 50
        else:
            state = working_mem.load()
            if state.get("pending_question") and route in (Route.FOLLOWUP, Route.NEW_TASK):
                working_mem.clear_pending_question()

        # Build enriched context
        context = build_enriched_context(message, dialog_key, history, working_mem, effective_route)
        result["context"] = context

        # Set max_iterations based on route
        if effective_route == Route.FOLLOWUP:
            result["max_iterations"] = 15
        elif effective_route == Route.SIMPLE:
            result["max_iterations"] = 0

        # Update working memory
        if effective_route == Route.NEW_TASK:
            working_mem.set_task(message[:500])
            result["working_mem_updated"] = True
        elif effective_route == Route.FOLLOWUP:
            from app.task_state import get_task_state_manager
            get_task_state_manager().set_dialogue_state(dialog_key, DialogueState.WORKING)
            result["working_mem_updated"] = True

        # For SIMPLE route: generate direct answer (no react loop)
        if effective_route == Route.SIMPLE:
            early_reply = _generate_simple_answer(message, history, working_mem, cfg)
            result["early_reply"] = early_reply

    except Exception:
        # Fallback: treat as new task, use original message
        result["route"] = Route.NEW_TASK
        result["context"] = message
        result["max_iterations"] = 50

    return result


def _generate_simple_answer(
    message: str,
    history: List[Dict],
    working_mem: WorkingMemory,
    cfg: Dict[str, Any],
) -> Optional[str]:
    """
    Generate a direct LLM answer for simple/reaction messages.
    No react loop. Uses last context for continuity.
    """
    try:
        from app.llm_router import LLMRouter

        state = working_mem.load()
        task_desc = state.get("task_desc", "") or ""
        notes = state.get("working_notes", [])
        if isinstance(notes, str):
            try:
                notes = json.loads(notes)
            except Exception:
                notes = []

        context_parts = []
        if task_desc:
            context_parts.append(f"Wir haben gerade gearbeitet an: {task_desc}")
        if notes and isinstance(notes, list):
            context_parts.append("Bereits gefunden: " + "; ".join(str(n) for n in notes[:3]))

        # Last 2 turns for immediate context
        recent = history[-4:] if history else []
        for item in recent:
            role = "Nutzer" if item.get("role") == "user" else "K.AI"
            text = str(item.get("text", "")).strip()[:200]
            if text:
                context_parts.append(f"{role}: {text}")

        system = (
            "Du bist K.AI, ein freundlicher KI-Assistent. "
            "Antworte kurz und natürlich auf die Nachricht des Nutzers. "
            "Nutze den Kontext um eine sinnvolle Antwort zu geben."
        )

        if context_parts:
            prompt = (
                system
                + "\n\nKONTEXT:\n"
                + "\n".join(context_parts)
                + f"\n\nNutzer: {message}\nK.AI:"
            )
        else:
            prompt = system + f"\n\nNutzer: {message}\nK.AI:"

        router = LLMRouter(cfg)
        resp = router.chat(prompt=prompt)
        text = resp.text if hasattr(resp, "text") else str(resp)
        if text and len(text.strip()) > 2:
            return text.strip()
    except Exception:
        pass
    return None


def on_react_loop_complete(
    dialog_key: str,
    success: bool,
    final_reply: str,
    steps: List[Dict],
) -> None:
    """
    Called after react loop completes. Updates working memory.
    Call this from _chat_reply after react loop returns.
    """
    try:
        working_mem = WorkingMemory(dialog_key)
        working_mem.complete(success=success, final_reply=final_reply)
        # Fix 2: Nach Abschluss auf IDLE zurücksetzen, damit das Routing beim
        # nächsten Turn nicht mehr WORKING/AWAITING_INPUT sieht.
        working_mem.set_dialogue_state(DialogueState.IDLE)

        # Extract key facts from successful steps and store as working notes
        if success and steps:
            for step in steps[-5:]:
                result_text = str(step.get("reply", "") or step.get("result", "")).strip()
                if result_text and len(result_text) > 20 and step.get("ok"):
                    note = result_text.split("\n")[0][:150]
                    if note:
                        working_mem.add_note(note)
    except Exception:
        pass
