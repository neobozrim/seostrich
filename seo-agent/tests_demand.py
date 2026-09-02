"""Two rules that keep a tagline from becoming a content pillar.

Observed 2026-09-01 on the Product Pirates run: the model chose "hugging face
the ai community building the future" — a Hugging Face tagline — as the head
of a cluster whose members were three 0-volume seeds and four 10-volume
tagline variants. The cluster was named after it and then SELECTED, because
"community" sounded relevant. Nothing in the data supported it.

Rule 1: the head term is measured — highest volume, then shortest — and a
phrase over five words never fronts a cluster while a real query sits beside it.
Rule 2: a cluster with no keyword at or above the demand floor cannot be
selected, however relevant it sounds — unless EVERY cluster is under the floor
(a thin market), in which case the floor is waived and that fact is recorded.
"""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.tools import cluster_keywords as ck  # noqa: E402
from src.tools import select_clusters as sc  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


# ---- the real members, with the real volumes -------------------------------
members = [
    "building the epistemic community of ai safety",        # 10, 7 words
    "hugging face the ai community building the future",    # 10, 8 words  <- what the model picked
    "ai community building the future",                     # 10, 5 words
    "the ai community building the future",                 # 10, 6 words
    "AI building community",                                # 0
    "AI community events",                                  # 0
    "AI PM community",                                      # 0
]
stats = {m.lower(): {"keyword": m, "volume": v} for m, v in zip(members, [10, 10, 10, 10, 0, 0, 0])}

print("1. head term")
head = ck._pick_head(members, stats)
ok(head == "ai community building the future", f"shortest of the top-volume ties wins, got {head!r}")
ok(len(head.split()) <= ck.HEAD_MAX_WORDS, "the head is not a sentence")

# a real query beside a tagline: the tagline loses even at equal volume
s2 = {"ai evals": {"volume": 50}, "the complete guide to ai evals for product teams": {"volume": 50}}
ok(ck._pick_head(list(s2), s2) == "ai evals", "a 5-word cap beats an 8-word phrase at equal volume")
# higher volume still wins over shorter
s3 = {"ai product manager course": {"volume": 320}, "ai course": {"volume": 40}}
ok(ck._pick_head(list(s3), s3) == "ai product manager course", "volume beats brevity")
# all zero: shortest
s4 = {"AI PM community": {"volume": 0}, "AI community events": {"volume": 0}}
# Both are 3 words at 0 volume, so the deterministic alphabetical tie-break decides.
ok(ck._pick_head(list(s4), s4) == "AI community events", "with no volume anywhere, the shortest phrase wins, ties alphabetical")
# only long phrases exist: still returns one rather than nothing
s5 = {"a b c d e f g": {"volume": 10}, "h i j k l m n o": {"volume": 30}}
ok(ck._pick_head(list(s5), s5) == "h i j k l m n o", "if everything is long, the highest volume long phrase is used")

# _expand uses it, ignoring the model's proposed head
ranked = [{"keyword": m, "volume": stats[m.lower()]["volume"]} for m in members]
raw = {"clusters": [{"id": 1, "name": "Community future", "head": "hugging face the ai community building the future",
                     "kw": members}]}
out = ck._expand(raw, ranked)
ok(out[0]["head_term"] == "ai community building the future", "_expand overrides the model's tagline head")

print("2. demand floor")
def cluster(name, max_vol, top):
    return {"cluster_name": name, "head_term": top, "keywords": [top],
            "metrics": {"max_volume": max_vol, "total_volume": max_vol,
                        "top_keywords": [{"keyword": top, "volume": max_vol}]}}

scored = {"scored_clusters": [
    cluster("Core PM learning", 320, "ai product manager course"),
    cluster("Community future", 10, "ai community building the future"),
    cluster("Builder hands-on", 40, "hands-on AI course"),
]}
eligible, dropped, note = sc._apply_demand_floor(scored)
ok([c["cluster_name"] for c in eligible["scored_clusters"]] == ["Core PM learning", "Builder hands-on"],
   "the 10-volume cluster is removed from what the model may select")
ok(len(dropped) == 1 and dropped[0]["cluster_name"] == "Community future", "it is pre-discarded")
ok("10 searches/month" in dropped[0]["reason"] and "ai community building the future" in dropped[0]["reason"],
   "the reason names the keyword and the measured number")
ok("promote it back" in dropped[0]["reason"], "the reason says it is parked, not deleted")
ok(dropped[0].get("demand_floor") is True, "the discard is marked as a floor decision, not a model judgement")
ok(note == "", "no thin-market note when the floor applies")

# thin market: everything under the floor -> waived, and said so
thin = {"scored_clusters": [cluster("A", 10, "a"), cluster("B", 10, "b")]}
eligible, dropped, note = sc._apply_demand_floor(thin)
ok(len(eligible["scored_clusters"]) == 2 and dropped == [], "in a thin market nothing is discarded")
ok("thin market" in note and "waived" in note, "and the waiver is recorded")

# everything above: untouched, no note
rich = {"scored_clusters": [cluster("A", 100, "a"), cluster("B", 50, "b")]}
eligible, dropped, note = sc._apply_demand_floor(rich)
ok(len(eligible["scored_clusters"]) == 2 and dropped == [] and note == "", "nothing to do when all clear the floor")

# old-shape cluster without a metrics block still works
legacy = {"clusters": [{"cluster_name": "L", "head_term": "x", "avg_volume": 5}]}
eligible, dropped, note = sc._apply_demand_floor(legacy)
ok(dropped == [] and "thin market" in note, "a legacy cluster is measured from avg_volume")

print("3. end to end through select_clusters")
fake_llm = {"selected": [{"cluster_name": "Core PM learning", "reason": "core"}],
            "discarded": [{"cluster_name": "Builder hands-on", "reason": "overlap"}]}
seen = {}
def fake_chat(user_msg, **kw):
    seen["msg"] = user_msg
    return "ok"
with patch.object(sc.llm, "chat", fake_chat), patch.object(sc.llm, "parse_json_response", lambda r: fake_llm):
    res = sc.select_clusters(scored, business_description="AI community for product people")
ok(res["success"], "selection succeeds")
ok("Community future" not in seen["msg"], "the model never saw the sub-floor cluster")
names = [d["cluster_name"] for d in res["selection"]["discarded"]]
ok(names == ["Builder hands-on", "Community future"], f"model discards first, then floor discards, got {names}")
ok("note" not in res["selection"], "no note when the floor applied normally")

with patch.object(sc.llm, "chat", fake_chat), patch.object(sc.llm, "parse_json_response",
                                                           lambda r: {"selected": [{"cluster_name": "A", "reason": "closest"}], "discarded": []}):
    res = sc.select_clusters(thin, business_description="x")
ok("thin market" in res["selection"].get("note", ""), "thin-market waiver surfaces in the selection")

print(f"demand: {PASS} assertions passed")
