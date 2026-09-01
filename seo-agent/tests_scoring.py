"""Cluster metrics must be measured from the keyword rows, never estimated.

The LLM scorer this replaces produced numbers that contradicted the data it was
given: on a real run it rated "PM Tools" (670 total volume, avg KD 2.2) the
strongest SEO opportunity, above "PM Core Concepts" (4,360 volume, KD 15.1).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tools.score_clusters import score_clusters, _metrics, _opportunity

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


UNIVERSE = [
    {"keyword": "ai product manager", "volume": 3600, "difficulty": 9, "cpc": 11.88, "intent": "informational"},
    {"keyword": "ai pm jobs", "volume": 1900, "difficulty": 0, "cpc": 2.0, "intent": "transactional"},
    {"keyword": "knowledge graph tutorial", "volume": 90, "difficulty": 4, "cpc": 0.0, "intent": "informational"},
    {"keyword": "knowledge graph python", "volume": 10, "difficulty": 2, "cpc": 0.5, "intent": "commercial"},
]
CLUSTERS = {"clusters": [
    {"cluster_name": "AI PM", "keywords": ["ai product manager", "ai pm jobs"]},
    {"cluster_name": "KG", "keywords": ["knowledge graph tutorial", "knowledge graph python"]},
]}

print("1. metrics are arithmetic over the real rows")
res = score_clusters(CLUSTERS, keywords=UNIVERSE)
by = {c["cluster_name"]: c["metrics"] for c in res["scored_clusters"]}
chk("AI PM total volume", by["AI PM"]["total_volume"] == 5500, str(by["AI PM"]["total_volume"]))
chk("AI PM max volume", by["AI PM"]["max_volume"] == 3600)
chk("AI PM avg difficulty", by["AI PM"]["avg_difficulty"] == 4.5, str(by["AI PM"]["avg_difficulty"]))
chk("AI PM max cpc", by["AI PM"]["max_cpc"] == 11.88)
chk("KG total volume", by["KG"]["total_volume"] == 100)
chk("KG commercial share", by["KG"]["commercial_share"] == 0.5, str(by["KG"]["commercial_share"]))
chk("AI PM commercial share", by["AI PM"]["commercial_share"] == 0.5)
chk("top_keywords ordered by volume",
    by["AI PM"]["top_keywords"][0]["keyword"] == "ai product manager")

print("2. bigger volume ranks higher — the failure the LLM scorer produced")
names = [c["cluster_name"] for c in res["scored_clusters"]]
chk("higher-volume cluster first", names[0] == "AI PM", str(names))
chk("no invented composite", not any(
    k in res["scored_clusters"][0] for k in ("seo_score", "geo_score", "combined_score")))
chk("method states metrics are computed", "no model estimated them" in res["method"])

print("3. the opportunity label states its own rule")
for m, expect in [
    ({"total_volume": 5000, "avg_difficulty": 10}, "high"),
    ({"total_volume": 500, "avg_difficulty": 90}, "medium"),
    ({"total_volume": 50, "avg_difficulty": 1}, "low"),
    ({"total_volume": 0, "avg_difficulty": 0}, "no volume data"),
    ({"total_volume": 5000, "avg_difficulty": 80}, "medium"),  # volume alone isn't enough
]:
    got = _opportunity(m)
    chk(f"vol={m['total_volume']:>5} kd={m['avg_difficulty']:>4} -> {expect}",
        got["opportunity"] == expect, got["opportunity"])
    chk("   rule is stated", bool(got["opportunity_rule"]))

print("4. degrades safely")
chk("no keywords -> zeros", _metrics([])["total_volume"] == 0)
chk("no division by zero", _metrics([])["avg_difficulty"] == 0.0)
chk("missing universe still works",
    score_clusters(CLUSTERS)["scored_clusters"][0]["metrics"]["keyword_count"] == 2)
chk("clusters holding dicts work",
    score_clusters({"clusters": [{"cluster_name": "X", "keywords": [
        {"keyword": "a", "volume": 10, "difficulty": 5, "cpc": 1.0, "intent": "commercial"}]}]}
    )["scored_clusters"][0]["metrics"]["total_volume"] == 10)
chk("non-list input rejected", "error" in score_clusters({"clusters": "nope"}))
chk("empty input safe", score_clusters({})["scored_clusters"] == [])

print("5. no LLM is involved")
src = Path("src/tools/score_clusters.py").read_text(encoding="utf-8")
chk("does not import llm", "import llm" not in src)
chk("makes no chat call", "llm.chat" not in src)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
