"""Every LLM call must have a deadline, and mechanical nodes must not pay for
reasoning they do not need.

Context (measured 2026-09-01, 72-keyword clustering call):
  qwen3.8-max    254.6s  10,358 output tokens (9,464 reasoning) -> 10 clusters
  qwen3.8-flash   44.1s   4,960 output tokens (4,051 reasoning) -> 10 clusters
max_tokens=2500 did not cap either, so the lever is model choice, not budgets.
The original code paired max_tokens=4500 with a fixed 120s timeout — a deadline
the call could not meet — which is why clustering failed on every full run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import llm
from src.config import settings

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


print("1. there is a deadline, and it is generous")
chk("default timeout defined", isinstance(llm.DEFAULT_TIMEOUT, float))
chk("longer than the observed 254s worst case", llm.DEFAULT_TIMEOUT > 254.6,
    f"{llm.DEFAULT_TIMEOUT}s")
chk("not unbounded (a hung call must not block a run)", llm.DEFAULT_TIMEOUT <= 600)

print("2. calls accept a per-call override")
import inspect
for fn in (llm.chat, llm.chat_stream):
    chk(f"{fn.__name__} takes timeout", "timeout" in inspect.signature(fn).parameters)
    chk(f"{fn.__name__} takes model", "model" in inspect.signature(fn).parameters)

print("3. the mechanical node runs on the fast model")
chk("fast model configured", bool(settings.qwen_model_fast))
src = Path("src/tools/cluster_keywords.py").read_text(encoding="utf-8")
chk("clustering requests the fast model", "qwen_model_fast" in src)
chk("clustering no longer hardcodes a short timeout", "timeout=120" not in src)

print("4. no node pairs a large budget with the old 120s deadline")
NODES = ["cluster_keywords", "validate_clusters", "score_clusters",
         "select_clusters", "recommend_pillars", "extract_seeds"]
for node in NODES:
    text = Path(f"src/tools/{node}.py").read_text(encoding="utf-8")
    explicit = re.search(r"timeout\s*=\s*([\d.]+)", text)
    deadline = float(explicit.group(1)) if explicit else llm.DEFAULT_TIMEOUT
    chk(f"{node:<18} deadline {deadline:5.0f}s", deadline >= 254.6,
        "too short for an observed worst case")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
