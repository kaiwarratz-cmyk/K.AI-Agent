"""
Memory Consolidation System for K.AI Agent.
Periodically merges fragmented memories into cohesive knowledge units using LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional


class MemoryConsolidator:
    def __init__(self, cfg: Dict[str, Any], memory_store):
        self.cfg = cfg
        self.ms = memory_store

    def consolidate_all(self, limit_per_kind: int = 50) -> str:
        """Konsolidiert alle Fakten-Typen."""
        try:
            # 1. Fakten sammeln
            facts = self.ms.get_all_facts(limit=100) # Vereinfachte Version
            if not facts or len(facts) < 10:
                return "Nicht genügend Fakten für Konsolidierung."

            # 2. Konsolidierungs-Logik
            res = self._run_llm_consolidation(facts)
            
            # 3. Alte Fakten löschen & Neue schreiben
            if res and "consolidated" in res:
                # In der Vollversion würden wir IDs löschen
                # self.ms.delete_facts(ids=[f['id'] for f in facts])
                for f in res["consolidated"]:
                    self.ms.add_fact(f, kind="consolidated", confidence=0.9)
                return f"{len(res['consolidated'])} Fakten konsolidiert."
        except Exception as e:
            return f"Fehler bei Konsolidierung: {str(e)}"
        return "Konsolidierung fehlgeschlagen."

    def _run_llm_consolidation(self, facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Nutzt das LLM um Fakten zu mergen."""
        from app.llm_router import LLMRouter
        router = LLMRouter(self.cfg)
        
        # Sicherstellen, dass wir Text-Inhalte extrahieren
        # (ChromaDB Resultate haben oft 'text' oder 'content')
        fact_texts = []
        for f in facts[:30]:
            txt = f.get("text") or f.get("content") or ""
            if txt:
                fact_texts.append(f"- {txt}")
        
        if not fact_texts:
            return {"consolidated": []}
            
        text_block = "\n".join(fact_texts)
        
        prompt = f"""Fasse die folgenden Fakten prägnant zusammen. 
Dedupliziere Informationen und erstelle eine strukturierte Liste von Kernwissen.

FAKTEN:
{text_block}

Gib die konsolidierten Fakten als JSON-Liste zurück:
{{"consolidated": ["Fakt 1", "Fakt 2"]}}"""

        try:
            res = router.chat_json(prompt, "consolidation", schema={
                "type": "object",
                "properties": {
                    "consolidated": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["consolidated"]
            })
            return res if res else {"consolidated": []}
        except Exception:
            return {"consolidated": []}
