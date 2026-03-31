"""
Intelligentes Tool-Management-System für K.AI Agent.
Vollständig integriert mit LLM-Capabilities und Provider-spezifischen Features.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
from pathlib import Path


class SmartToolManager:
    """
    Zentrales intelligentes Tool-Management mit LLM-Integration.
    - Auto-Discovery aus Registry
    - Provider-spezifische Optimierung (native tools, JSON schemas)
    - Dynamische Tool-Selection basierend auf Intent
    - LLM-Capability-aware (nutzt native function calling wenn verfügbar)
    """
    
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._summary_cache: Optional[str] = None
        self._llm_router = None
        # OPT-8: Cache auch für intent-gefilterte Tool-Listen
        self._intent_cache: Dict[str, List[Dict[str, Any]]] = {}

    
    def _get_router(self):
        """Lazy-load LLMRouter für Integration."""
        if self._llm_router is None:
            from app.llm_router import LLMRouter
            self._llm_router = LLMRouter(self.cfg)
        return self._llm_router
    
    def get_tools_for_llm(
        self, 
        intent: Optional[str] = None,
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
        use_native_calling: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Intelligente Tool-Selection mit vollständiger LLM-Integration.
        
        Args:
            intent: Optional - filtere Tools nach Intent
            provider_id: Optional - Provider-ID (gemini, openai, etc.)
            model: Optional - Model-Name
            use_native_calling: Nutze native Function-Calling wenn verfügbar
        
        Returns:
            List von Tool-Definitionen im OpenAI-Function-Calling-Format
        """
        from app.tool_registry import get_all_tools, get_tools_for_intent
        from app.tool_profiles import resolve_tool_profile
        
        # 1. Bestimme Provider-Info
        llm_cfg = self.cfg.get("llm", {})
        provider_id = provider_id or str(llm_cfg.get("active_provider_id", "")).strip()
        model = model or str(llm_cfg.get("active_model", "")).strip()
        
        providers = self.cfg.get("providers", {})
        provider_type = ""
        if provider_id and providers.get(provider_id):
            provider_type = str(providers[provider_id].get("type", "")).strip().lower()
        
        # 2. Hole Tool-Profile für Provider
        profile = resolve_tool_profile(provider_type, model, provider_id)
        
        # 3. Base-Tools holen (mit Intent-Filter) – OPT-8: Intent-Cache
        if intent:
            if intent not in self._intent_cache:
                self._intent_cache[intent] = get_tools_for_intent(intent)
            tools = self._intent_cache[intent].copy()
        else:
            if self._tools_cache is None:
                self._tools_cache = get_all_tools()
            tools = self._tools_cache.copy()

        
        # 4. Prüfe ob Provider native Tool-Calling unterstützt
        supports_native = False
        if profile and use_native_calling:
            native_cfg = profile.get("native_tools", {})
            supports_native = bool(native_cfg.get("enabled", False))
        
        # 5. Provider-spezifische Optimierung
        if supports_native:
            tools = self._optimize_for_provider(tools, profile, provider_type)
        else:
            # Fallback: Prompt-basierte Tools (für alte LLMs)
            tools = self._convert_to_prompt_format(tools)
        
        return tools
    
    def _optimize_for_provider(
        self, 
        tools: List[Dict[str, Any]], 
        profile: Dict[str, Any],
        provider_type: str
    ) -> List[Dict[str, Any]]:
        """Optimiert Tool-Schemas für spezifische Provider und deren LLM-Capabilities."""
        import copy
        
        schema_cfg = profile.get("native_tools", {}).get("schema", {})
        strip_add_props = bool(schema_cfg.get("strip_additional_properties", False))
        max_tools = int(schema_cfg.get("max_tools_per_call", 100))
        
        # Deep-Copy für Modifikationen
        optimized = copy.deepcopy(tools[:max_tools])
        
        # Provider-spezifische Anpassungen
        if provider_type == "gemini":
            # Gemini: Keine additionalProperties, TYPE in Uppercase
            for tool in optimized:
                if "function" in tool and "parameters" in tool["function"]:
                    self._optimize_for_gemini(tool["function"]["parameters"])
        
        elif provider_type == "anthropic":
            # Claude: Nutzt input_schema statt parameters
            for tool in optimized:
                if "function" in tool:
                    func = tool["function"]
                    if "parameters" in func:
                        func["input_schema"] = func.pop("parameters")
        
        elif provider_type in ["openai_compatible", "xai"]:
            # OpenAI/Grok: Standard-Format, aber strict mode nutzen wenn verfügbar
            if strip_add_props:
                for tool in optimized:
                    if "function" in tool and "parameters" in tool["function"]:
                        self._strip_additional_properties(tool["function"]["parameters"])
        
        return optimized
    
    def _optimize_for_gemini(self, schema: Dict[str, Any]) -> None:
        """Gemini-spezifische Schema-Optimierung."""
        if not isinstance(schema, dict):
            return
        
        # Entferne additionalProperties
        if "additionalProperties" in schema:
            del schema["additionalProperties"]
        
        # TYPE in Uppercase (Gemini-Requirement)
        if "type" in schema and isinstance(schema["type"], str):
            schema["type"] = schema["type"].upper()
        
        # Rekursiv für properties
        if "properties" in schema and isinstance(schema["properties"], dict):
            for prop_schema in schema["properties"].values():
                self._optimize_for_gemini(prop_schema)
        
        # Rekursiv für items (Arrays)
        if "items" in schema:
            self._optimize_for_gemini(schema["items"])
    
    def _strip_additional_properties(self, schema: Dict[str, Any]) -> None:
        """Entfernt additionalProperties rekursiv."""
        if not isinstance(schema, dict):
            return
        
        if "additionalProperties" in schema:
            del schema["additionalProperties"]
        
        if "properties" in schema and isinstance(schema["properties"], dict):
            for prop_schema in schema["properties"].values():
                self._strip_additional_properties(prop_schema)
        
        if "items" in schema:
            self._strip_additional_properties(schema["items"])
    
    def _convert_to_prompt_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Konvertiert Tools in Prompt-Format für LLMs ohne native Function-Calling."""
        # Für Legacy-LLMs: Vereinfachte Tool-Beschreibung
        prompt_tools = []
        for tool in tools:
            func = tool.get("function", {})
            prompt_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {})
            })
        return prompt_tools
    
    def execute_tool_call_with_llm(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_context: str = ""
    ) -> Tuple[bool, Any, str]:
        """
        Führt Tool-Call aus mit LLM-Unterstützung bei Fehlern.
        
        Returns:
            (success, result, error_message)
        """
        from app.tool_registry import validate_tool_call
        
        # 1. Validiere Tool-Call
        valid, error = validate_tool_call(tool_name, args)
        
        if not valid:
            # LLM-basierte Fehlerkorrektur versuchen
            corrected = self._llm_correct_tool_call(tool_name, args, error, user_context)
            if corrected:
                tool_name, args = corrected
                valid, error = validate_tool_call(tool_name, args)
        
        if not valid:
            return False, None, f"Validation failed: {error}"
        
        # 2. Tool ausführen (über main.py _execute_action)
        # Wird von aufrufendem Code gemacht
        return True, None, ""
    
    def _llm_correct_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        error: str,
        user_context: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Nutzt LLM um fehlerhafte Tool-Calls zu korrigieren."""
        try:
            router = self._get_router()
            
            prompt = f"""Ein Tool-Call ist fehlgeschlagen. Bitte korrigiere ihn.

FEHLER: {error}

TOOL: {tool_name}
ARGUMENTE: {json.dumps(args, indent=2)}

USER-KONTEXT: {user_context[:200]}

Gib den korrigierten Tool-Call als JSON zurück:
{{"tool": "tool_name", "args": {{"param": "value"}}}}"""

            schema = {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"}
                },
                "required": ["tool", "args"],
                "additionalProperties": False
            }
            
            result = router.chat_json(
                prompt=prompt,
                schema_name="tool_correction",
                schema=schema
            )
            
            if result and isinstance(result, dict):
                return result.get("tool"), result.get("args", {})
        
        except Exception:
            pass
        
        return None
    
    def get_tool_summary(
        self, 
        intent: Optional[str] = None,
        max_tools: int = 15,
        format: str = "detailed"  # "detailed", "compact", "llm-optimized"
    ) -> str:
        """
        Generiert LLM-optimierte Tool-Übersicht.
        
        Args:
            intent: Filtere nach Intent
            max_tools: Max. Anzahl Tools
            format: detailed (mit Beschreibung), compact (nur Namen), 
                   llm-optimized (strukturiert für besseres Understanding)
        """
        from app.tool_registry import get_tools_for_intent, get_all_tools
        
        # Cache-Check
        cache_key = f"{intent}_{max_tools}_{format}"
        if not intent and format == "detailed" and self._summary_cache:
            return self._summary_cache
        
        # Hole relevante Tools
        if intent:
            tools = get_tools_for_intent(intent)
        else:
            tools = get_all_tools()
        
        tools = tools[:max_tools]
        
        if format == "compact":
            names = [t.get("function", {}).get("name", "") for t in tools]
            return "Tools: " + ", ".join(n for n in names if n)
        
        elif format == "llm-optimized":
            # Strukturiert für optimales LLM-Understanding
            lines = ["# AVAILABLE TOOLS\n"]
            for i, tool in enumerate(tools, 1):
                func = tool.get("function", {})
                name = func.get("name", "")
                desc = func.get("description", "")
                params = func.get("parameters", {}).get("properties", {})
                
                lines.append(f"{i}. **{name}**")
                lines.append(f"   Purpose: {desc}")
                
                if params:
                    req = func.get("parameters", {}).get("required", [])
                    param_strs = []
                    for pname, pschema in params.items():
                        ptype = pschema.get("type", "any")
                        required = " (required)" if pname in req else ""
                        param_strs.append(f"{pname}: {ptype}{required}")
                    lines.append(f"   Parameters: {', '.join(param_strs)}")
                lines.append("")
            
            return "\n".join(lines)
        
        else:  # detailed
            lines = ["VERFÜGBARE TOOLS:"]
            for tool in tools:
                func = tool.get("function", {})
                name = func.get("name", "")
                desc = func.get("description", "")
                
                if name and desc:
                    if len(desc) > 80:
                        desc = desc[:77] + "..."
                    lines.append(f"- {name}: {desc}")
            
            result = "\n".join(lines)
            if not intent and format == "detailed":
                self._summary_cache = result
            
            return result
    
    def suggest_tools_for_query(
        self, 
        query: str, 
        top_k: int = 5,
        use_llm: bool = True
    ) -> List[str]:
        """
        Intelligente Tool-Suggestion mit optionaler LLM-Unterstützung.
        
        Args:
            query: User-Anfrage
            top_k: Anzahl Suggestions
            use_llm: Nutze LLM für bessere Suggestions
        """
        if use_llm:
            return self._llm_suggest_tools(query, top_k)
        else:
            return self._keyword_suggest_tools(query, top_k)
    
    def _llm_suggest_tools(self, query: str, top_k: int) -> List[str]:
        """LLM-basierte Tool-Suggestion."""
        try:
            from app.tool_registry import get_tool_names
            
            router = self._get_router()
            tool_names = get_tool_names()
            
            prompt = f"""Welche Tools sind relevant für diese Anfrage?

ANFRAGE: {query}

VERFÜGBARE TOOLS: {', '.join(tool_names[:20])}

Wähle die {top_k} relevantesten Tools. Antwort als JSON-Array: ["tool1", "tool2"]"""

            schema = {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["tools"],
                "additionalProperties": False
            }
            
            result = router.chat_json(
                prompt=prompt,
                schema_name="tool_suggestion",
                schema=schema
            )
            
            if result and isinstance(result, dict):
                return result.get("tools", [])[:top_k]
        
        except Exception:
            pass
        
        return self._keyword_suggest_tools(query, top_k)
    
    def _keyword_suggest_tools(self, query: str, top_k: int) -> List[str]:
        """Keyword-basierte Tool-Suggestion als Fallback."""
        from app.tool_registry import get_all_tools
        
        query_lower = query.lower()
        tools = get_all_tools()
        
        scored = []
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "").lower()
            
            score = 0
            keywords = {
                ("datei", "file"): ["file", "read", "write"],
                ("suche", "search", "web"): ["search", "web"],
                ("script", "code"): ["script"],
                ("liste", "list"): ["list"],
            }
            
            for query_kws, tool_kws in keywords.items():
                if any(kw in query_lower for kw in query_kws):
                    if any(tk in name for tk in tool_kws):
                        score += 3
            
            if score > 0:
                scored.append((name, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in scored[:top_k]]


# Globale Instanz (Singleton-Pattern)
_tool_manager: Optional[SmartToolManager] = None


def get_tool_manager(cfg: Dict[str, Any]) -> SmartToolManager:
    """Singleton-Pattern für Tool-Manager."""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = SmartToolManager(cfg)
    return _tool_manager
