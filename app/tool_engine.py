from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

_ERROR_LOG_FILE = Path(__file__).resolve().parent.parent / "data" / "logs" / "errors.log"


@dataclass
class ToolEvent:
    tool: str
    note: str
    created_at: str


class ToolLogStore:
    def __init__(self, max_items: int = 200):
        self.max_items = max_items
        self._events: List[ToolEvent] = []
        self._sources: List[Dict[str, Any]] = []
        self.log_fn: Optional[Callable[[str, str], None]] = None

    def log(self, tool: str, note: str) -> None:
        # Spam frühzeitig ausfiltern, bevor er ins UI (_events) oder File wandert
        skip_audit = {"messenger", "execution_plane", "mcp_refresh", "llm_test", "cron_jobs_api", "webui", "config", "audit"}
        if tool in skip_audit:
            return

        ts = datetime.now(timezone.utc).isoformat()
        self._events.insert(
            0,
            ToolEvent(
                tool=tool,
                note=note,
                created_at=ts,
            ),
        )
        self._events = self._events[: self.max_items]
        
        # Audit Log persistieren
        try:
            audit_file = Path(__file__).resolve().parent.parent / "data" / "logs" / "audit.log"
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps(
                {"ts": ts, "kind": tool, "message": note},
                ensure_ascii=False,
            )
            with audit_file.open("a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

        # Externer Logger (z.B. CLI-Anzeige)
        if self.log_fn:
            try:
                self.log_fn(tool, note)
            except Exception:
                pass

        # Alle *_error Events auch in errors.log persistieren
        if "error" in str(tool).lower():
            try:
                _ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                entry = json.dumps(
                    {"ts": ts, "kind": tool, "message": note},
                    ensure_ascii=False,
                )
                with _ERROR_LOG_FILE.open("a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except Exception:
                pass

    def add_source(self, source: Dict[str, Any]) -> None:
        self._sources.insert(0, source)
        self._sources = self._sources[: self.max_items]

    def recent_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        return [event.__dict__ for event in self._events[:limit]]

    def recent_sources(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self._sources[:limit]


# Module-level default tool store
tool_store = ToolLogStore()
