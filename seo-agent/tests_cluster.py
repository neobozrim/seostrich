"""Cluster node: index expansion offline, then one live call on real keywords.

The live half matters: this node timed out on every full run of the project,
so a green unit test alone would prove nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tools.cluster_keywords import _expand, _resolve, cluster_keywords

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RANKED = [
    {"keyword": "ai product management", "volume": 900, "difficulty": 40, "intent": "informational"},
    {"keyword": "how to evaluate llms", "volume": 500, "difficulty": 30, "intent": "informational"},
    {"keyword": "agentic commerce", "volume": 300, "difficulty": 20, "intent": "commercial"},
    {"keyword": "knowledge graph tutorial", "volume": 100, "difficulty": 10, "intent": "informational"},
]

print("1. index resolution")
chk("1-based index", _resolve(1, RANKED) == "ai product management")
chk("last index", _resolve(4, RANKED) == "knowledge graph tutorial")
chk("out of range -> None", _resolve(99, RANKED) is None)
chk("zero -> None", _resolve(0, RANKED) is None)
chk("numeric string", _resolve("2", RANKED) == "how to evaluate llms")
chk("literal phrase still accepted", _resolve("agentic commerce", RANKED) == "agentic commerce")
chk("bool rejected", _resolve(True, RANKED) is None)

print("2. expansion computes stats from the real keyword rows")
raw = {"clusters": [
    {"id": 1, "name": "AI PM", "head": 1, "kw": [1, 2], "intent": "informational", "why": "core role topics"},
    {"id": 2, "name": "Commerce", "head": 3, "kw": [3], "intent": "commercial", "why": "buying agents"},
]}
out = _expand(raw, RANKED)
chk("two clusters", len(out) == 2, str(out))
chk("members resolved", out[0]["keywords"] == ["ai product management", "how to evaluate llms"])
chk("head resolved", out[0]["head_term"] == "ai product management")
chk("avg volume", out[0]["avg_volume"] == 700, str(out[0]["avg_volume"]))
chk("avg difficulty", out[0]["avg_difficulty"] == 35, str(out[0]["avg_difficulty"]))
chk("rationale carried", out[0]["rationale"] == "core role topics")

print("3. malformed input degrades instead of exploding")
chk("empty -> []", _expand({}, RANKED) == [])
chk("garbage list -> []", _expand(["nope", 3], RANKED) == [])
chk("all-invalid indices dropped", _expand({"clusters": [{"kw": [99, 100]}]}, RANKED) == [])
chk("bare list accepted", len(_expand([{"name": "X", "kw": [1]}], RANKED)) == 1)

print("4. output size: indices vs echoing keyword text")
idx_payload = json.dumps(raw, ensure_ascii=False)
text_payload = json.dumps({"clusters": [
    {"cluster_id": 1, "cluster_name": "AI PM", "head_term": "ai product management",
     "keywords": ["ai product management", "how to evaluate llms"],
     "intent": "informational", "rationale": "core role topics"},
    {"cluster_id": 2, "cluster_name": "Commerce", "head_term": "agentic commerce",
     "keywords": ["agentic commerce"], "intent": "commercial", "rationale": "buying agents"},
]}, ensure_ascii=False)
print(f"     index form: {len(idx_payload):>4} chars | text form: {len(text_payload):>4} chars "
      f"({100 - len(idx_payload) * 100 // len(text_payload)}% smaller)")
chk("index form is smaller", len(idx_payload) < len(text_payload))

if "--live" in sys.argv:
    print("5. LIVE: real keywords from the run that timed out")
    kw_file = Path("cluster_input.json")
    if kw_file.exists():
        keywords = json.loads(kw_file.read_text(encoding="utf-8"))
    else:
        keywords = [{"keyword": f"ai product topic {i}", "volume": 500 - i * 5,
                     "difficulty": i % 60, "intent": "informational"} for i in range(72)]
    print(f"     clustering {len(keywords)} keywords...")
    t = time.time()
    res = cluster_keywords(keywords, max_clusters=10, location_code=2840, language_code="en")
    elapsed = time.time() - t
    chk(f"live call succeeded in {elapsed:.1f}s", res.get("success"), str(res.get("error"))[:180])
    chk("under the old 120s timeout", elapsed < 120, f"took {elapsed:.1f}s")
    if res.get("success"):
        cl = res["clusters"]
        chk("produced clusters", len(cl) >= 5, f"got {len(cl)}")
        real = {k["keyword"] for k in keywords}
        invented = [m for c in cl for m in c["keywords"] if m not in real]
        chk("no invented keywords", not invented, str(invented[:3]))
        for c in cl[:4]:
            print(f"       - {c['cluster_name']}: {len(c['keywords'])} kw, "
                  f"head={c['head_term'][:40]!r}, vol~{c['avg_volume']}")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
