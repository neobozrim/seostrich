"""Braintrust integration for conversation tracing and self-improvement suggestions."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, List, Optional

import requests

from ..config import settings
from .. import memory


# ── Session list cache (5-minute TTL to avoid repeated pagination) ──
_session_cache: dict[str, Any] = {"data": None, "expires": 0}
_CACHE_TTL = 300  # seconds

# ── Trace disk cache (avoid re-fetching traces we've already read) ──
# Lives in the shared memory dir so all agents/state land in one place.
def _get_trace_cache_dir() -> Path:
    return memory._get_memory_dir() / "traces"
_TRACE_CACHE_TTL = 3600  # 1 hour


def _is_test_session(session_id: str) -> bool:
    """Check if a session ID is a test/debug session that should be excluded."""
    return session_id.startswith(("test-", "debug-", "error-"))


def _truncate_result(result: Any, max_chars: int = 500) -> str:
    """Truncate a tool result to fit Braintrust's payload limits."""
    if result is None:
        return ""
    result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
    if len(result_str) > max_chars:
        return result_str[:max_chars] + f"... [truncated, {len(result_str)} total chars]"
    return result_str


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


def _get_api_credentials():
    """Get API key and project ID for Braintrust API calls."""
    api_key = settings.braintrust_api_key or os.getenv('BRAINTRUST_API_KEY')
    project_id = settings.braintrust_project_id or os.getenv('BRAINTRUST_PROJECT_ID')
    if not api_key:
        return None, None
    return api_key, project_id


def _fetch_project_logs(limit: int = 50, cursor: Optional[str] = None, retries: int = 3) -> dict:
    """Fetch project logs from Braintrust using the official API.

    Uses POST /v1/project_logs/{project_id}/fetch endpoint.
    Retries with exponential backoff on 429 rate limit errors.

    Returns:
        Dict with 'events' list and optional 'cursor' for pagination
    """
    api_key, project_id = _get_api_credentials()
    if not api_key or not project_id:
        print("⚠ Braintrust API key or project ID not configured")
        return {"events": []}

    url = f"https://api.braintrust.dev/v1/project_logs/{project_id}/fetch"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload: dict[str, Any] = {"limit": limit}
    if cursor:
        payload["cursor"] = cursor

    for attempt in range(retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                if attempt < retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"⚠ Braintrust rate limit, retrying in {wait_time}s (attempt {attempt + 1}/{retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print("⚠ Braintrust rate limit exceeded, giving up")
                    return {"events": []}
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            body = e.response.text[:200] if e.response is not None else ""
            print(f"⚠ Braintrust API error: {e} - {body}")
            return {"events": []}
        except Exception as e:
            print(f"⚠ Failed to fetch logs: {e}")
            return {"events": []}
    
    return {"events": []}


def _extract_session_id(event: dict) -> Optional[str]:
    """Extract session_id from a Braintrust event (metadata or input)."""
    meta = event.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("session_id"):
        return meta["session_id"]
    event_input = event.get("input")
    if isinstance(event_input, dict) and event_input.get("session_id"):
        return event_input["session_id"]
    return None


def _build_trace_from_event(event: dict, session_id: str) -> dict:
    """Build a trace dict from a Braintrust event."""
    event_input = event.get("input") or {}
    event_output = event.get("output") or {}
    metadata = event.get("metadata") or {}

    messages = []
    if isinstance(event_input, dict):
        messages = event_input.get("messages", [])

    tool_results = []
    if isinstance(event_output, dict):
        tool_details = event_output.get("tool_details", [])
        if tool_details:
            tool_results = tool_details
        else:
            for tool_name in event_output.get("tools_used", []):
                tool_results.append({"tool": tool_name})

    # Extract user_request — prefer metadata, then input
    user_request = ""
    if isinstance(metadata, dict):
        user_request = metadata.get("user_request", "")
    if not user_request and isinstance(event_input, dict):
        user_request = event_input.get("user_request", "")

    return {
        "session_id": session_id,
        "user_request": user_request,
        "messages": messages,
        "tool_results": tool_results,
        "metadata": metadata,
        "tags": event.get("tags", []),
        "created": event.get("created"),
        "id": event.get("id"),
    }


def read_braintrust_trace(session_id: str) -> Optional[dict]:
    """Read a specific trace from Braintrust by session ID.

    Checks disk cache first (1 hour TTL). If not cached, fetches recent events
    via POST /v1/project_logs/{project_id}/fetch with retry logic.
    Prefers the main log event (with messages) over span events.

    Args:
        session_id: The session identifier to look up

    Returns:
        Trace data dict or None if not found
    """
    # Check disk cache first
    trace_cache_dir = _get_trace_cache_dir()
    trace_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = trace_cache_dir / f"{session_id}.json"
    
    if cache_file.exists():
        # Check if cache is fresh (less than 1 hour old)
        cache_age = time.time() - cache_file.stat().st_mtime
        if cache_age < _TRACE_CACHE_TTL:
            try:
                cached_trace = json.loads(cache_file.read_text(encoding="utf-8"))
                return cached_trace
            except (json.JSONDecodeError, OSError):
                pass  # Cache corrupted, fetch fresh
    
    # Fetch from API with retry logic
    cursor = None
    first_match = None

    for _ in range(4):  # Up to 4 pages of 50 events
        result = _fetch_project_logs(limit=50, cursor=cursor)
        events = result.get("events", [])
        if not events:
            break

        for event in events:
            if _extract_session_id(event) == session_id:
                # Check if this event has messages (main log vs span)
                event_input = event.get("input") or {}
                if isinstance(event_input, dict) and event_input.get("messages"):
                    trace = _build_trace_from_event(event, session_id)
                    # Write to cache
                    try:
                        cache_file.write_text(json.dumps(trace, indent=2), encoding="utf-8")
                    except OSError:
                        pass  # Cache write failed, not critical
                    return trace
                # Keep first match as fallback
                if first_match is None:
                    first_match = event

        cursor = result.get("cursor")
        if not cursor:
            break

    if first_match:
        trace = _build_trace_from_event(first_match, session_id)
        # Write to cache
        try:
            cache_file.write_text(json.dumps(trace, indent=2), encoding="utf-8")
        except OSError:
            pass
        return trace
    
    return None


def list_recent_sessions(limit: int = 5) -> List[str]:
    """List recent session IDs from Braintrust traces.

    Filters out test/debug sessions and uses a 5-minute cache.

    Args:
        limit: Maximum number of sessions to return

    Returns:
        List of session IDs (most recent first, test sessions excluded)
    """
    # Check cache
    if _session_cache["data"] and time.time() < _session_cache["expires"]:
        return _session_cache["data"][:limit]

    session_ids: list[str] = []
    cursor = None

    for _ in range(4):  # Up to 4 pages
        result = _fetch_project_logs(limit=50, cursor=cursor)
        events = result.get("events", [])
        if not events:
            break

        for event in events:
            sid = _extract_session_id(event)
            if sid and sid not in session_ids and not _is_test_session(sid):
                session_ids.append(sid)
                if len(session_ids) >= limit * 2:
                    # Fetch extra in case caller wants more later
                    break

        cursor = result.get("cursor")
        if not cursor or len(session_ids) >= limit * 2:
            break

    # Cache the full list
    _session_cache["data"] = session_ids
    _session_cache["expires"] = time.time() + _CACHE_TTL

    return session_ids[:limit]


def log_conversation(
    session_id: str,
    messages: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    metadata: dict[str, Any] = None,
) -> dict:
    """Log a conversation to Braintrust for tracing and analysis.

    Creates a hierarchical trace:
        session (queryable log event + visualization span)
          └─ turn 0 (one per agent round)
               ├─ tool: read_memory
               └─ tool: keyword_research
          └─ turn 1
               └─ tool: draft_article

    Args:
        session_id: Unique session identifier
        messages: List of message dicts with role/content
        tool_results: List of tool call results (each has a 'round' field)
        metadata: Additional metadata to attach
    """
    logger = _get_braintrust_logger()
    if not logger:
        return {
            "status": "skipped",
            "reason": "Braintrust not available (pip install braintrust + set BRAINTRUST_API_KEY)",
        }

    try:
        # Extract user request summary — prefer metadata (passed by caller), then messages
        user_request = ""
        if metadata and metadata.get("user_request"):
            user_request = metadata["user_request"]
        if not user_request:
            for msg in messages:
                if msg.get("role") == "user":
                    user_request = msg.get("content", "")[:200]
                    break

        assistant_reply = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                assistant_reply = msg["content"][:500]
                break

        # Normalize tool results: add success/error fields, truncate large results
        normalized_tool_results = []
        for tr in tool_results:
            norm = {
                "tool": tr.get("tool", "unknown"),
                "round": tr.get("round", 0),
                "args": tr.get("args", {}),
                "success": tr.get("success", tr.get("error") is None and tr.get("result") is not None),
                "error": tr.get("error"),
                "result": _truncate_result(tr.get("result")),
            }
            normalized_tool_results.append(norm)

        # Build structured metadata
        tools_used = sorted(set(t.get("tool", "") for t in normalized_tool_results))
        successful_tools = sum(1 for t in normalized_tool_results if t.get("success"))
        failed_tools = sum(1 for t in normalized_tool_results if not t.get("success"))
        meta = {
            "session_id": session_id,
            "user_request": user_request,
            "tool_count": len(normalized_tool_results),
            "tools_used": tools_used,
            "message_count": len(messages),
            "successful_tools": successful_tools,
            "failed_tools": failed_tools,
        }
        if metadata:
            for k, v in metadata.items():
                if k not in meta:
                    meta[k] = v

        # ── Main log event (what read_braintrust_trace reads back) ──
        logger.log(
            input={"session_id": session_id, "messages": messages, "user_request": user_request},
            output={
                "assistant_reply": assistant_reply,
                "tool_calls": len(normalized_tool_results),
                "tools_used": tools_used,
                "tool_details": normalized_tool_results,
            },
            metadata=meta,
            tags=["seo-agent", "conversation", f"tools:{len(normalized_tool_results)}"],
        )

        # ── Hierarchical spans for dashboard visualization ──
        session_span = logger.start_span(name=f"session-{session_id[:12]}")
        session_span.log(
            input={"user_request": user_request, "session_id": session_id},
            output={"assistant_reply": assistant_reply},
            metadata=meta,
        )

        # Group tool_results by round
        rounds: dict[int, list[dict]] = {}
        for tr in normalized_tool_results:
            r = tr.get("round", 0)
            rounds.setdefault(r, []).append(tr)

        # Create one turn span per round, with tool calls nested inside
        for round_num in sorted(rounds.keys()):
            round_tools = rounds[round_num]
            round_tools_names = [t.get("tool", "?") for t in round_tools]

            turn_span = session_span.start_span(
                name=f"turn-{round_num}",
            )
            turn_span.log(
                input={"turn": round_num, "tools_in_turn": round_tools_names},
                output={"tool_count": len(round_tools)},
                metadata={"turn": round_num, "tools": round_tools_names},
                tags=[f"turn:{round_num}"],
            )

            # Tool call spans inside this turn
            for tr in round_tools:
                tool_span = turn_span.start_span(
                    name=f"tool:{tr.get('tool', 'unknown')}",
                )
                tool_span.log(
                    input={"tool": tr.get("tool"), "args": tr.get("args", {})},
                    output={
                        "result": tr.get("result", ""),
                        "success": tr.get("success"),
                        "error": tr.get("error"),
                    },
                    metadata={
                        "tool": tr.get("tool"),
                        "turn": round_num,
                        "success": tr.get("success"),
                    },
                    tags=["tool-call", tr.get("tool", "unknown")],
                )
                tool_span.end()

            turn_span.end()

        session_span.end()
        logger.flush()

        total_spans = 1 + len(rounds) + len(normalized_tool_results)
        return {"status": "success", "logged_to": "braintrust", "spans": total_spans}
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
