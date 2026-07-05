from __future__ import annotations

from typing import Any, Callable

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "fn": fn,
        }
        return fn
    return decorator


def get_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_REGISTRY.values()
    ]


def call_tool(name: str, arguments: str | dict) -> Any:
    import json
    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {name}")
    return TOOL_REGISTRY[name]["fn"](**args)
