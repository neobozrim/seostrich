from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .config import settings

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
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
) -> dict[str, Any]:
    """Call Qwen via OpenAI-compatible API. Accepts a string or list of message dicts."""
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

    resp = get_client().chat.completions.create(**kwargs)
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
