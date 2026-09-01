"""Offline sanity check for cluster payload trim + bounded retry (no LLM/DFS)."""
import sys, types

# Stub heavy transitive imports so we can import the tool modules standalone.
from src.tools import cluster_keywords as ck
from src.tools import strategy_pipeline as sp

calls = {"n": 0, "fail_first": 0}

def fake_cluster_keywords(keywords, max_clusters=10, location_code=None, language_code=None):
    calls["n"] += 1
    if calls["n"] <= calls["fail_first"]:
        return {"success": False, "error": "LLM clustering failed: timeout", "clusters": None}
    return {"success": True, "clusters": [
        {"cluster_id": 1, "cluster_name": "Beans", "head_term": "specialty beans",
         "keywords": ["specialty beans", "roast"], "intent": "commercial",
         "avg_volume": 100, "avg_difficulty": 10, "rationale": "core product"}
    ]}

# 1) payload: numbered keywords, capped at 80, with a deadline it can meet.
#    Was: "- kw" lines and max_tokens=4500 against a fixed 120s timeout, which
#    at the model's real throughput could not complete. Keywords are now sent
#    as a numbered list and returned by index, so the reply stays short.
orig_chat = ck.llm.chat
captured = {}
def fake_chat(messages, system=None, tools=None, temperature=0.3,
              max_tokens=8000, model=None, timeout=None):
    captured["max_tokens"] = max_tokens
    captured["timeout"] = timeout
    captured["msg"] = messages
    return {"content": '{"clusters": []}', "usage": {}}
ck.llm.chat = fake_chat
kws = [{"keyword": f"kw{i}", "volume": i, "difficulty": 1, "intent": "informational"} for i in range(120)]
ck.cluster_keywords(kws, max_clusters=10)
lines = [l for l in captured["msg"].splitlines() if l and l[0].isdigit() and ". kw" in l]
assert len(lines) == 80, f"expected 80 keyword lines, got {len(lines)}"
assert lines[0].startswith("1. kw119"), "expected highest volume first, got " + lines[0]
assert captured["max_tokens"] == 2500, f"expected max_tokens 2500, got {captured['max_tokens']}"
assert captured["timeout"] and captured["timeout"] >= 2500 / 11.7, (
    f"deadline {captured['timeout']} cannot cover a full-budget reply")
ck.llm.chat = orig_chat
print("PASS payload: 80 numbered lines, volume desc, max_tokens=2500, deadline covers the budget")

# 2) _cluster_with_retry: success on first try -> 1 call
sp.cluster_keywords = fake_cluster_keywords
calls.update(n=0, fail_first=0)
r = sp._cluster_with_retry([{"keyword": "x"}], 2840, "en")
assert r["success"] and calls["n"] == 1, f"expected 1 call, got {calls['n']}"
print("PASS retry helper: success path makes exactly 1 call")

# 3) fail first, succeed second -> 2 calls, returns success
calls.update(n=0, fail_first=1)
r = sp._cluster_with_retry([{"keyword": "x"}], 2840, "en")
assert r["success"] and calls["n"] == 2, f"expected 2 calls, got {calls['n']}"
print("PASS retry helper: transient failure retried once -> success (2 calls)")

# 4) fail both -> 2 calls, returns failure (no infinite retry)
calls.update(n=0, fail_first=99)
r = sp._cluster_with_retry([{"keyword": "x"}], 2840, "en")
assert (not r["success"]) and calls["n"] == 2, f"expected 2 calls then fail, got {calls['n']}"
print("PASS retry helper: persistent failure bounded at 2 calls then fail-fast")

print("ALL PASS")
