"""Tool results are not truncated to uselessness, and reads are not repeated.

Two defaults from the project's first commit, never revisited:
  - every tool result cut at 4,000 characters, silently and mid-JSON. Measured
    on a real run that removed 70% of list_clusters_all (13,366 chars), 51% of
    cluster_keywords and 42% of the keyword table — so the model received
    fragments of its own tool output and called the same tools again.
  - no caching of read-only tools, so re-listing clusters across rounds
    re-read and re-serialised the same payload every time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src import agent

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


print("1. real tool results now arrive whole")
# sizes measured from the last strategy run
REAL = {
    "list_clusters_all": 13366,
    "cluster_keywords": 8186,
    "seo_get_keywords": 6896,
    "pull_universe": 6869,
    "ai_citability_brief": 1794,
}
for tool, n in REAL.items():
    payload = "x" * n
    out = agent._tool_result_for_model(payload, tool)
    chk(f"{tool:<22} {n:>6,} chars survives", out == payload and "TRUNCATED" not in out,
        f"lost {n - len(out)}")
chk("the old cap would have cut all but one",
    sum(1 for n in REAL.values() if n > 4000) == 4, "")

print("2. an outlier is bounded, and SAYS it was bounded")
huge = "y" * 40000
out = agent._tool_result_for_model(huge, "list_clusters_all")
chk("bounded", len(out) < len(huge))
chk("marked, not silent", "TRUNCATED" in out)
chk("says how big it was", "40,000" in out)
chk("points at the alternative", "read_run_section" in out)
chk("tells it not to just re-call", "do NOT call" in out.lower() or "do not call" in out.lower())

print("3. cache keys are stable and argument-sensitive")
k1 = agent._cache_key("list_clusters_all", {"run_id": "r1"})
k2 = agent._cache_key("list_clusters_all", {"run_id": "r1"})
k3 = agent._cache_key("list_clusters_all", {"run_id": "r2"})
chk("same args, same key", k1 == k2)
chk("different args, different key", k1 != k3)
chk("key order does not matter",
    agent._cache_key("t", {"a": 1, "b": 2}) == agent._cache_key("t", {"b": 2, "a": 1}))
chk("unserialisable args do not crash", agent._cache_key("t", {"x": object()}) is not None)

print("4. the right tools are cached, and mutations invalidate")
chk("cluster listing is cached", "list_clusters_all" in agent.CACHEABLE_TOOLS)
chk("the paid citation check is cached", "ai_citation_check" in agent.CACHEABLE_TOOLS)
chk("section reads are cached", "read_run_section" in agent.CACHEABLE_TOOLS)
for mutator in ("promote_cluster", "discard_cluster", "propose_cluster",
                "rerun_cluster_research"):
    chk(f"{mutator:<24} invalidates", mutator in agent.CACHE_INVALIDATING_TOOLS)
chk("the graphs invalidate too",
    {"run_keyword_strategy", "run_geo_demand"} <= agent.CACHE_INVALIDATING_TOOLS)
chk("nothing is both cached and invalidating",
    not (agent.CACHEABLE_TOOLS & agent.CACHE_INVALIDATING_TOOLS),
    str(agent.CACHEABLE_TOOLS & agent.CACHE_INVALIDATING_TOOLS))

print("5. no mutating tool is cached by accident")
MUTATORS = {"confirm_market", "submit_deliverable", "promote_cluster",
            "discard_cluster", "propose_cluster"}
chk("none of them cacheable", not (MUTATORS & agent.CACHEABLE_TOOLS),
    str(MUTATORS & agent.CACHEABLE_TOOLS))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
