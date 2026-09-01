"""Clusters are verified against what Google returns, not what words look alike.

Measured on real SERPs (2026-09-01, US/EN):
  "ai product manager course" vs "ai product manager certification"  0.89  -> same page
  "ai product manager course" vs "ai product manager coursera"       0.22  -> separate
  "knowledge graphs for AI products" vs "knowledge graph RAG"        0.00  -> separate

A thematic clusterer gets the first wrong (four competing pages) and the third
wrong the other way (one page ranking for neither).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tools import serp_verify as sv

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


print("1. overlap is computed on the page, not the link")
chk("protocol and www ignored",
    sv._bare("https://www.Coursera.org/x/") == sv._bare("http://coursera.org/x"))
chk("path is kept", sv._bare("a.com/one") != sv._bare("a.com/two"))
chk("identical sets score 1.0", sv.overlap(["a", "b"], ["a", "b"]) == 1.0)
chk("disjoint sets score 0.0", sv.overlap(["a"], ["b"]) == 0.0)
chk("empty is 0.0, never a crash", sv.overlap([], ["a"]) == 0.0)
chk("scored against the smaller set",
    sv.overlap(["a", "b"], ["a", "b", "c", "d"]) == 1.0)

print("2. only look-alike pairs are worth paying for")
heads = ["ai product manager course", "ai product manager certification", "remote access home computer"]
pairs = sv._candidate_pairs(heads)
chk("the look-alike pair is a candidate", (0, 1) in pairs, str(pairs))
chk("the unrelated one is not", (0, 2) not in pairs and (1, 2) not in pairs, str(pairs))
chk("nothing to check means no calls",
    sv.verify_clusters([{"head_term": "alpha"}, {"head_term": "zulu"}], 2840, "en")["checked"] == 0)

print("3. merges follow the SERPs, using the real measurements")
calls = []


def fake_top(keyword, loc, lang):
    calls.append(keyword)
    base = [f"coursera.org/{i}" for i in range(9)]
    return {
        # 0.89: nearly the same results
        "ai product manager course": base + ["a.com/x"],
        "ai product manager certification": base + ["b.com/y"],
        # 0.22: same words, different intent
        "ai product manager coursera": ["z.com/1", "z.com/2", "coursera.org/0"] + [f"z.com/{i}" for i in range(3, 10)],
    }.get(keyword, [])


sv.top_urls = fake_top
clusters = [
    {"cluster_name": "Courses", "head_term": "ai product manager course", "keywords": ["k1"]},
    {"cluster_name": "Certification", "head_term": "ai product manager certification", "keywords": ["k2"]},
    {"cluster_name": "Coursera", "head_term": "ai product manager coursera", "keywords": ["k3"]},
]
v = sv.verify_clusters(clusters, 2840, "en")
merged_pairs = {(m["a"], m["b"]) for m in v["merges"]}
chk("high overlap merges",
    ("ai product manager course", "ai product manager certification") in merged_pairs,
    str(merged_pairs))
chk("low overlap stays separate",
    any(k["a"] == "ai product manager course" and "coursera" in k["b"] for k in v["kept_separate"]),
    str(v["kept_separate"]))
chk("the evidence is published", all("shared_results" in m for m in v["merges"]))
chk("and the reason is in words", all("same results" in m["why"] for m in v["merges"]))
chk("threshold is stated", v["threshold"] == sv.MERGE_THRESHOLD)

print("4. merging folds keywords together and records why")
out = sv.apply_merges(clusters, v)
chk("three clusters became two", len(out) == 2, str([c.get("cluster_name") for c in out]))
merged = next(c for c in out if c.get("merged_from"))
chk("both names recorded", len(merged["merged_from"]) == 2, str(merged["merged_from"]))
chk("keywords combined", set(merged["keywords"]) == {"k1", "k2"}, str(merged["keywords"]))
chk("no keyword duplicated", len(merged["keywords"]) == len(set(merged["keywords"])))
chk("the reason travels with it", "same results" in merged["merge_reason"])
chk("the separate cluster is untouched",
    any(c.get("cluster_name") == "Coursera" and not c.get("merged_from") for c in out))

print("5. running out of budget keeps clusters apart, never merges blind")
unverified = [k for k in v["kept_separate"] if k["overlap"] is None]
v2 = sv.verify_clusters(clusters, 2840, "en", max_calls=0)
chk("no calls means no merges", not v2["merges"], str(v2["merges"]))
chk("and it says why", all("not verified" in k["why"] for k in v2["kept_separate"]),
    str(v2["kept_separate"][:1]))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
