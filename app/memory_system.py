"""
Hierarchisches Gedaechtnis-System fuer K.AI Agent.
Unterstuetzt persistente Core- und Session-Memory mit Ziel-Tracking.
"""
from __future__ import annotations

import json
import time
import os
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

class MemoryManager:
    def __init__(self, cfg: Dict[str, Any], memory_store=None):
        self.cfg = cfg
        self.ms = memory_store
        self.root_dir = Path(__file__).parent.parent
        self.core_memory_path = self.root_dir / "data" / "core_memory.json"
        self.sessions_dir = self.root_dir / "data" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_dialog_key = "default"
        self.session_state = self._empty_session()
        self._ensure_paths()

    def _empty_session(self):
        return {
            "summary": "",
            "entities": {},
            "active_goal": "Kein aktives Ziel.",
            "updated_at": 0
        }

    def _ensure_paths(self):
        self.core_memory_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.core_memory_path.exists():
            self.core_memory_path.write_text(json.dumps({
                "user": {}, "devices": {}, "preferences": {}, "permanent_facts": {}
            }, indent=2), encoding="utf-8")

    def load_session(self, dialog_key: str):
        self.current_dialog_key = dialog_key or "default"
        path = self.sessions_dir / f"{self.current_dialog_key}.json"
        self.session_state = self._empty_session()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict): self.session_state.update(data)
            except: pass

    def save_session(self):
        path = self.sessions_dir / f"{self.current_dialog_key}.json"
        self.session_state["updated_at"] = time.time()
        path.write_text(json.dumps(self.session_state, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_core_memory(self) -> Dict[str, Any]:
        try:
            return json.loads(self.core_memory_path.read_text(encoding="utf-8"))
        except: return {}

    def update_core_memory(self, category: str, key: str, value: Any):
        core = self.get_core_memory()
        if category not in core: core[category] = {}
        core[category][key] = value
        self.core_memory_path.write_text(json.dumps(core, indent=2, ensure_ascii=False), encoding="utf-8")

    def update_session_state(self, summary: str = None, entities: Dict = None, active_goal: str = None):
        if summary: self.session_state["summary"] = summary
        if entities: self.session_state["entities"].update(entities)
        if active_goal: self.session_state["active_goal"] = active_goal
        self.save_session()

    def build_hierarchical_context(self, query: str, recent_history: List[Dict[str, str]]) -> str:
        parts = []
        
        # 1. SESSION CONTEXT (Highest priority for flow)
        if self.session_state["summary"] or self.session_state["entities"]:
            s_parts = []
            if self.session_state["active_goal"]: s_parts.append(f"Ziel: {self.session_state['active_goal']}")
            if self.session_state["summary"]: s_parts.append(f"Zusammenfassung: {self.session_state['summary']}")
            parts.append("### AKTUELLER SITZUNGS-STATUS\n" + "\n".join(s_parts))
        
        # 2. CORE MEMORY (Facts)
        core = self.get_core_memory()
        core_lines = []
        # Flatten for better attention
        for cat, val in core.items():
            if isinstance(val, dict):
                for k, v in val.items(): core_lines.append(f"- {k}: {v}")
            elif val: core_lines.append(f"- {cat}: {val}")
        
        if core_lines: parts.append("### GLOBALER WISSENSSPEICHER\n" + "\n".join(core_lines[:15]))
        
        # 3. WORKING MEMORY
        hist = [f"{'NUTZER' if t['role']=='user' else 'AGENT'}: {t['content']}" for t in recent_history[-6:]]
        if hist: parts.append("### LETZTE NACHRICHTEN\n" + "\n".join(hist))
        
        return "\n\n".join(parts)
