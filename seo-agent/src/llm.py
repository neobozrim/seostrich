from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from openai import OpenAI

from .config import settings

_client: OpenAI | None = None

_pace_lock = threading.Lock()
_last_call = 0.0


def _pace() -> None:
    """Enforce LLM_MIN_INTERVAL_SECONDS between calls (token-plan queues bursts)."""
    global _last_call
    interval = settings.llm_min_interval
    if interval <= 0:
        return
    with _pace_lock:
        now = time.monotonic()
        wait = _last_call + interval - now
        _last_call = now + max(wait, 0.0)
    if wait > 0:
        time.sleep(wait)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=120.0,  # 2 minute timeout for LLM calls
            # SDK default retries twice on timeout — a queued/hung request
            # would then block a run for ~7 min. Fail fast; the agent loop
            # surfaces the error as a tool result instead.
            max_retries=1,
        )
    return _client


def chat(
    messages: str | list[dict[str, str]],
    *,
    system: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 8000,
    model: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Call Qwen via OpenAI-compatible API. Accepts a string or list of message dicts.

    ``timeout`` overrides the client default for this call. Needed because the
    default (120s) is shorter than a large generation takes: measured output
    speed is ~37 tok/s, so any call allowed 4500 tokens needs ~121s and times
    out exactly when the model uses its budget.
    """
    if isinstance(messages, str):
        msgs: list[dict[str, str]] = [{"role": "user", "content": messages}]
    else:
        msgs = list(messages)

    if system:
        msgs.insert(0, {"role": "system", "content": system})

    kwargs: dict[str, Any] = {
        "model": model or settings.qwen_model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    if settings.mock_llm:
        return {
            "content": "[]",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    _pace()
    client = get_client()
    if timeout is not None:
        client = client.with_options(timeout=timeout)
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    result: dict[str, Any] = {
        "content": choice.message.content or "",
        "usage": {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
        },
    }
    if choice.message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in choice.message.tool_calls
        ]
    return result


def chat_stream(
    messages: str | list[dict[str, str]],
    *,
    system: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 8000,
    model: str | None = None,
    timeout: float | None = None,
):
    """Same as chat(), but yields text as the model produces it.

    Yields {"type": "delta", "content": str} for each text fragment, then a
    final {"type": "final", "content": str, "tool_calls": [...]} carrying the
    assembled result in chat()'s shape.

    Worth the extra code path: latency here tracks OUTPUT tokens, so a long
    answer blocks for a minute before anything appears. Measured 2026-09-01 on
    the same prompt — 17.6s to complete, but the first chunk at 2.1s.
    """
    if isinstance(messages, str):
        msgs: list[dict[str, str]] = [{"role": "user", "content": messages}]
    else:
        msgs = list(messages)
    if system:
        msgs.insert(0, {"role": "system", "content": system})

    kwargs: dict[str, Any] = {
        "model": model or settings.qwen_model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    if settings.mock_llm:
        yield {"type": "final", "content": "[]", "tool_calls": []}
        return

    _pace()
    content_parts: list[str] = []
    # Tool calls arrive as indexed deltas that must be concatenated.
    partial: dict[int, dict[str, Any]] = {}

    client = get_client()
    if timeout is not None:
        client = client.with_options(timeout=timeout)
    for event in client.chat.completions.create(**kwargs):
        if not event.choices:
            continue
        delta = event.choices[0].delta
        if delta is None:
            continue
        if delta.content:
            content_parts.append(delta.content)
            yield {"type": "delta", "content": delta.content}
        for tc in (delta.tool_calls or []):
            slot = partial.setdefault(
                tc.index, {"id": "", "name": "", "arguments": ""}
            )
            if tc.id:
                slot["id"] = tc.id
            if tc.function and tc.function.name:
                slot["name"] += tc.function.name
            if tc.function and tc.function.arguments:
                slot["arguments"] += tc.function.arguments

    result: dict[str, Any] = {
        "type": "final",
        "content": "".join(content_parts),
        "tool_calls": [partial[i] for i in sorted(partial) if partial[i]["name"]],
    }
    yield result


def parse_json_response(resp: dict[str, Any]) -> dict | list:
    """Extract JSON from an LLM response dict."""
    return extract_json(resp.get("content", ""))


def format_json(obj: Any, indent: int = 2) -> str:
    """Format a Python object as pretty JSON string."""
    return json.dumps(obj, indent=indent, ensure_ascii=False, default=str)


def extract_json(text: str) -> dict | list:
    """Robustly extract JSON from LLM text output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for m in (
        re.search(r"\{.*\}", text, re.DOTALL),
        re.search(r"\[.*\]", text, re.DOTALL),
    ):
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse JSON from LLM output: {text[:200]}")


def safe_parse_tool_args(arguments: Any) -> tuple[dict, str | None]:
    """Defensively parse LLM tool-call arguments.

    Returns (args, error): args is a dict on success; error is a short
    explanation when parsing fails (args is then {}). Applies the same
    repair heuristics as extract_json before giving up, so a malformed
    tool call becomes an error result the model can self-correct instead
    of an exception that kills the whole stream.
    """
    if arguments is None:
        return {}, None
    if isinstance(arguments, dict):
        return arguments, None
    if not isinstance(arguments, str):
        return {}, f"expected object or JSON string, got {type(arguments).__name__}"
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        try:
            parsed = extract_json(arguments)
        except (ValueError, TypeError):
            return {}, f"arguments are not valid JSON ({arguments[:120]}...)"
    if isinstance(parsed, dict):
        return parsed, None
    return {}, f"arguments parsed to {type(parsed).__name__}, expected an object"
