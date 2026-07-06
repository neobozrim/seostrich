from __future__ import annotations

from .. import llm


def web_search(query: str, context: str = "") -> dict:
    """Search the web using Qwen's web search capabilities."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for current information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                },
            },
        }
    ]

    messages = [{"role": "user", "content": query}]
    if context:
        messages[0]["content"] = f"Context: {context}\n\nSearch for: {query}"

    resp = llm.chat(messages, tools=tools, temperature=0.3)

    # If Qwen returns web search results, they'll be in the content
    return {
        "query": query,
        "results": resp.get("content", ""),
    }
