from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE_DIR = Path("data/workspace")

def mem_update_plan(content: str, plan_file: str = "plan.md") -> str:
    """Updates the central plan.md file in the workspace. The plan is the 'anchor' for the agent."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    p = WORKSPACE_DIR / plan_file
    try:
        p.write_text(content, encoding="utf-8")
        return f"Plan updated successfully in {p}. Use this as your primary guide for next steps."
    except Exception as e:
        return f"ERROR updating plan: {e}"

def mem_save_fact(key: str, fact: str) -> str:
    """Saves a discovered insight (e.g. an IP address or file path) to a persistent facts file."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    facts_file = WORKSPACE_DIR / "discovered_facts.json"
    
    try:
        facts = {}
        if facts_file.exists():
            facts = json.loads(facts_file.read_text(encoding="utf-8"))
        
        facts[key] = {
            "value": fact,
            "timestamp": os.path.getmtime(str(facts_file)) if facts_file.exists() else 0
        }
        
        facts_file.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"Fact saved: {key} = {fact}. This insight will persist across the session."
    except Exception as e:
        return f"ERROR saving fact: {e}"

def mem_get_facts() -> str:
    """Retrieves all saved facts from the current session."""
    facts_file = WORKSPACE_DIR / "discovered_facts.json"
    if not facts_file.exists():
        return "No facts saved yet."
    try:
        facts = json.loads(facts_file.read_text(encoding="utf-8"))
        lines = [f"- {k}: {v['value']}" for k, v in facts.items()]
        return "CURRENT DISCOVERED FACTS:\n" + "\n".join(lines)
    except Exception as e:
        return f"ERROR reading facts: {e}"
