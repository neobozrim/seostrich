"""The brief: a defined closing stage, built from measured stages, validated
against its shape, and rebuilt when the selection changes."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tmp = Path(tempfile.mkdtemp(prefix="seo-brief-"))
os.environ["SESSIONS_DIR"] = str(tmp)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
from src import runs  # noqa: E402
from src import cluster_governance as g  # noqa: E402
from src.tools import strategy_brief as sb
sb.dfs.serp_paa = lambda *a, **k: []  # no network in the suite
sb.dfs.serp_organic = lambda *a, **k: []  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


RID = "test-brief-run"
run = {
    "id": RID, "title": "Product Pirates Club", "project": "productpirates.club",
    "stages": [
        {"id": "intake", "artifact": {"market": "US-EN"}},
        {"id": "clusters", "artifact": {
            "clusters": [
                {"cluster_name": "Core PM learning", "name": "Core PM learning", "head_term": "ai product manager course",
                 "keywords": ["ai product manager course", "ai product manager certification"],
                 "keyword_stats": {"ai product manager course": {"volume": 320, "difficulty": 30, "owned_by": ["productschool.com"]},
                                   "ai product manager certification": {"volume": 720, "difficulty": 24}},
                 "metrics": {"total_volume": 1040, "max_volume": 720, "avg_difficulty": 27},
                 "selection_reason": "largest measured demand"},
                {"cluster_name": "Builder hands-on", "name": "Builder hands-on", "head_term": "hands-on AI course",
                 "keywords": ["hands-on AI course"], "keyword_stats": {"hands-on AI course": {"volume": 40, "difficulty": 10}},
                 "metrics": {"total_volume": 40, "max_volume": 40, "avg_difficulty": 10}},
            ],
            "discarded": [
                {"cluster_name": "Provider Coursera IBM", "name": "Provider Coursera IBM",
                 "discard_reason": "brand-specific course queries", "metrics": {"total_volume": 60}},
            ],
        }},
        {"id": "pillars", "artifact": {"pillars": [
            {"pillar_title": "AI PM Learning Hub", "pillar_type": "hub", "cluster_name": "Core PM learning", "priority": 1, "rationale": "biggest measured demand"},
        ]}},
    ],
}
runs.save_run(RID, run)

print("1. the input is assembled from the artefact")
inp = sb.build_input(runs.get_run(RID), "AI community for product people")
ok(inp["business"].startswith("AI community"), "business carried")
ok([c["cluster"] for c in inp["selected_clusters"]] == ["Core PM learning", "Builder hands-on"], "selected clusters in order")
ok(inp["selected_clusters"][0]["keywords"][0]["keyword"] == "ai product manager certification", "keywords sorted by volume")
ok(inp["parked"][0]["why"] == "brand-specific course queries", "parked carries the stated reason")
ok(inp["competitors_own"] == [{"who": "productschool.com", "keywords": ["ai product manager course"]}], "who owns what, from the tags")

print("2. validation")
good = {"the_call": {"pillar": "AI PM Learning Hub", "why": "1,040 total volume at KD 27"},
        "out_answer": [{"who": "productschool.com", "for_what": "the course query"}],
        "pieces": [{"title": "T", "question": "Q?", "cluster": "Core PM learning", "target_keyword": "ai product manager certification", "format": "guide"}],
        "parked": [{"cluster": "Provider Coursera IBM", "why": "brand-specific"}]}
ok(sb._valid(good, inp) == (True, ""), "a well-formed brief passes")
bad = dict(good, pieces=[dict(good["pieces"][0], target_keyword="something invented")])
ok(sb._valid(bad, inp)[0] is False and "not in input" in sb._valid(bad, inp)[1], "an invented target keyword is rejected")
ok(sb._valid(dict(good, the_call={}), inp)[0] is False, "a missing call is rejected")
ok(sb._valid(dict(good, pieces=[]), inp)[0] is False, "no pieces is rejected")

print("3. write_brief records the stage; a bad first answer is retried once")
answers = [bad, good]
with patch.object(sb.llm, "chat", lambda *a, **k: "x"), patch.object(sb.llm, "parse_json_response", lambda r: answers.pop(0)):
    res = sb.write_brief(RID, "AI community for product people")
ok(res["ok"], "brief produced after one rejection")
st = next(s for s in runs.get_run(RID)["stages"] if s["id"] == "brief")
ok(st["label"] == "The brief" and st["artifact"]["the_call"]["pillar"] == "AI PM Learning Hub", "recorded as the brief stage")
ok(st["artifact"]["stale"] is False and st["artifact"]["based_on"]["selected"] == ["Core PM learning", "Builder hands-on"], "fresh, and says what it was based on")

with patch.object(sb.llm, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))):
    res2 = sb.write_brief(RID)
ok(res2["ok"] is False and "boom" in res2["error"], "a failed model call is reported, not hidden")
ok(next(s for s in runs.get_run(RID)["stages"] if s["id"] == "brief")["artifact"]["the_call"]["pillar"] == "AI PM Learning Hub",
   "and the previous brief is kept")

print("4. a change to the selection marks the brief stale — and does NOT rebuild it")
calls = []
def fake_refresh(run_id):
    calls.append(run_id); return True
with patch.object(sb, "refresh_async", fake_refresh), patch.object(g.strategy_brief, "refresh_async", fake_refresh):
    r = g.discard_cluster(RID, "Builder hands-on", "too thin", by="user")
ok(r["ok"], "discard ok")
st = next(s for s in runs.get_run(RID)["stages"] if s["id"] == "brief")
ok(st["artifact"]["stale"] is True and "Builder hands-on" in st["artifact"]["stale_reason"], "brief marked stale with the reason")
ok(calls == [], "no rebuild is requested: the brief is on demand")

with patch.object(g.strategy_brief, "refresh_async", fake_refresh):
    g.promote_cluster(RID, "Builder hands-on", by="user")
    g.reset_run(RID, by="user")
ok(calls == [], "promote and reset mark stale without rebuilding either")

print("5. refresh_async really runs, once at a time")
answers2 = [good, good]
with patch.object(sb.llm, "chat", lambda *a, **k: "x"), patch.object(sb.llm, "parse_json_response", lambda r: dict(good)):
    first = sb.refresh_async(RID)
    second = sb.refresh_async(RID)
    for _ in range(50):
        if RID not in sb._refreshing:
            break
        time.sleep(0.05)
ok(first is True, "first refresh starts")
st = next(s for s in runs.get_run(RID)["stages"] if s["id"] == "brief")
ok(st["artifact"]["stale"] is False, "the background rebuild cleared the stale flag")

print(f"brief: {PASS} assertions passed")
