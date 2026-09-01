"""Time the agent's real first LLM call in isolation.

Reproduces exactly what run_agent round 1 sends: the full system prompt, the
intent-selected tool schemas, and the user message — so a stall can be
attributed to the model, the payload, or the agent loop rather than guessed at.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from openai import OpenAI

from src.agent import SYSTEM_PROMPT, select_tools_for_intent
from src.config import PROVIDER_BASE_URLS, settings

MSG = Path("pp_input.txt").read_text(encoding="utf-8")


def timed(label: str, model: str, tools: list, msg: str, stream: bool) -> None:
    client = OpenAI(api_key=settings.qwen_api_key,
                    base_url=PROVIDER_BASE_URLS[settings.provider],
                    timeout=300.0, max_retries=0)
    kwargs = dict(model=model,
                  messages=[{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": msg}],
                  temperature=0.3, max_tokens=8000)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    payload = len(json.dumps(kwargs, ensure_ascii=False, default=str))
    stop = threading.Event()

    def tick():
        n = 0
        while not stop.wait(15):
            n += 15
            print(f"      ...{n}s still waiting", flush=True)

    t = threading.Thread(target=tick, daemon=True); t.start()
    start = time.time()
    try:
        if stream:
            first = None
            chunks = 0
            for _ in client.chat.completions.create(stream=True, **kwargs):
                chunks += 1
                if first is None:
                    first = time.time() - start
                    print(f"      first chunk at {first:.1f}s", flush=True)
            print(f"  {label:38} OK  {time.time()-start:6.1f}s  "
                  f"({chunks} chunks, payload {payload//1024}KB, {len(tools)} tools)")
        else:
            r = client.chat.completions.create(**kwargs)
            m = r.choices[0].message
            calls = [c.function.name for c in (m.tool_calls or [])]
            print(f"  {label:38} OK  {time.time()-start:6.1f}s  "
                  f"payload {payload//1024}KB, {len(tools)} tools, "
                  f"in={r.usage.prompt_tokens} out={r.usage.completion_tokens} "
                  f"tool_calls={calls or '-'}")
    except Exception as exc:
        print(f"  {label:38} ERR {time.time()-start:6.1f}s  {type(exc).__name__}: {str(exc)[:120]}")
    finally:
        stop.set()


tools = select_tools_for_intent(MSG)
print(f"model={settings.qwen_model}  provider={settings.provider}  "
      f"tools={len(tools)}  msg={len(MSG)} chars\n")

timed("1. no tools, short msg", settings.qwen_model, [], "Say ok.", False)
timed("2. no tools, real msg", settings.qwen_model, [], MSG, False)
timed("3. REAL: tools + real msg", settings.qwen_model, tools, MSG, False)
timed("4. same, streaming", settings.qwen_model, tools, MSG, True)
timed("5. flash: tools + real msg", "qwen3.8-flash", tools, MSG, False)
