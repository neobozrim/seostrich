"""Braintrust integration for conversation tracing and self-improvement suggestions."""
from __future__ import annotations

import json
import os
from typing import Any

from ..config import settings


def _get_braintrust_logger():
    """Get Braintrust logger. Requires BRAINTRUST_API_KEY in env."""
    try:
        import braintrust
        api_key = settings.braintrust_api_key
        if not api_key:
            api_key = os.getenv('BRAINTRUST_API_KEY')
        if not api_key:
            return None
        logger = braintrust.init_logger(
            project='seo-agent',
            api_key=api_key
        )
        return logger
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠ Braintrust init failed: {e}")
        return None


def log_conversation(
    session_id: str,
    messages: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    metadata: dict[str, Any] = None,
) -> dict:
    """Log a conversation to Braintrust for tracing and analysis.

    Args:
        session_id: Unique session identifier
        messages: List of message dicts with role/content
        tool_results: List of tool call results
        metadata: Additional metadata to attach
    """
    logger = _get_braintrust_logger()
    if not logger:
        return {
            "status": "skipped",
            "reason": "Braintrust not available (pip install braintrust + set BRAINTRUST_API_KEY)",
        }

    try:
        logger.log(
            input={"session_id": session_id, "messages": messages},
            output={
                "tool_calls": len(tool_results),
                "tools_used": list(set(t.get("tool", "") for t in tool_results)),
            },
            metadata=metadata or {},
            tags=["seo-agent", "conversation"],
        )
        return {"status": "success", "logged_to": "braintrust"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def suggest_improvements(
    session_id: str,
    conversation_summary: str,
    memory_context: str,
) -> dict:
    """Analyze a run and suggest improvements to tools, prompts, or setup.

    Args:
        session_id: The session to analyze
        conversation_summary: Summary of what happened
        memory_context: Current memory state for context
    """
    from .. import llm

    system = """You are an AI agent self-improvement analyst. Review the conversation
and memory context to suggest improvements to:
1. Tool design (missing tools, redundant tools, better parameters)
2. System prompt (clarity, guidance, edge cases)
3. Memory usage (what should be recorded, patterns to learn)
4. Workflow efficiency (unnecessary steps, better sequencing)

Output JSON:
{
  "tool_improvements": ["suggestion1", "suggestion2"],
  "prompt_improvements": ["suggestion1"],
  "memory_improvements": ["suggestion1"],
  "workflow_improvements": ["suggestion1"],
  "priority": "which area needs most attention"
}"""

    user_msg = f"""Session: {session_id}
Summary: {conversation_summary}
Memory: {memory_context[:1000]}

Suggest improvements for the agent's setup."""

    resp = llm.chat(user_msg, system=system, temperature=0.4)
    return llm.parse_json_response(resp)
