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


def research_topic(topic: str, depth: str = "brief") -> dict:
    """Research a topic and return structured findings."""
    system = f"""You are a research assistant. Search for current information about the topic and provide {"detailed" if depth == "detailed" else "brief"} findings.

Output JSON:
{{
  "topic": "topic",
  "key_findings": ["finding1", "finding2"],
  "sources": [{{"title": "source", "url": "url", "summary": "brief"}}],
  "relevance": "why this matters"
}}"""

    user_msg = f"Research: {topic}"
    resp = llm.chat(user_msg, system=system, temperature=0.3)
    return llm.parse_json_response(resp)
