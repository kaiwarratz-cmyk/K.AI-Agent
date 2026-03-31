from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from app.config import load_config


mcp = FastMCP("K.AI MCP Tools", json_response=True)
_REGISTERED: Dict[str, Any] = {}


def _py_type_for_schema(schema: Dict[str, Any]) -> Any:
    t = str(schema.get("type", "") or "").lower()
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        return list
    if t == "object":
        return dict
    return str


if __name__ == "__main__":
    mcp.run(transport="stdio")
