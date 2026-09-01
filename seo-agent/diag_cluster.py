"""Compare models on the real clustering call, and count actual output tokens.

212.9s for a call capped at max_tokens=2500 does not add up at ~37 tok/s, so
measure what the model actually emits (reasoning tokens included) rather than
assuming.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from openai import OpenAI

from src.config import PROVIDER_BASE_URLS, settings
from src.tools.cluster_keywords import SYSTEM_PROMPT, _expand

keywords = json.loads(Path("cluster_input.json").read_text(encoding="utf-8"))
ranked = sorted(keywords, key=lambda k: k.get("volume") or 0, reverse=True)[:80]
kw_text = "\n".join(
    f"{i}. {k.get('keyword','')} (vol {k.get('volume',0)}, kd {k.get('difficulty',0)}, "
    f"{k.get('intent','unknown')})"
    for i, k in enumerate(ranked, 1)
)
user_msg = (
    f"Keywords (refer to these by number):\n{kw_text}\n"
    f"Target market: location_code 2840, language en.\n"
    f"Create 10 thematic clusters. Use keyword NUMBERS only in \"kw\" and \"head\". "
    f"Keep every \"why\" to one short sentence."
)

client = OpenAI(api_key=settings.qwen_api_key,
                base_url=PROVIDER_BASE_URLS[settings.provider],
                timeout=400.0, max_retries=0)

print(f"{len(ranked)} keywords, prompt {len(user_msg)} chars\n")

for model in ("qwen3.8-max", "qwen3.8-flash", "qwen3.6-plus"):
    t = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user_msg}],
            temperature=0.3, max_tokens=2500,
        )
        elapsed = time.time() - t
        u = r.usage
        reasoning = 0
        details = getattr(u, "completion_tokens_details", None)
        if details is not None:
            reasoning = getattr(details, "reasoning_tokens", 0) or 0
        text = r.choices[0].message.content or ""
        try:
            from src.llm import extract_json
            clusters = _expand(extract_json(text), ranked)
        except Exception:
            clusters = []
        rate = u.completion_tokens / elapsed if elapsed else 0
        print(f"  {model:14} {elapsed:6.1f}s  out={u.completion_tokens:>5} "
              f"(reasoning {reasoning:>5})  {rate:4.0f} tok/s  -> {len(clusters)} clusters")
        for c in clusters[:3]:
            print(f"       {c['cluster_name'][:42]:<42} {len(c['keywords']):>2} kw")
    except Exception as exc:
        print(f"  {model:14} {time.time()-t:6.1f}s  ERR {type(exc).__name__}: {str(exc)[:90]}")
