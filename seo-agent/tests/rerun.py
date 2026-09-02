"""Re-researching ONE cluster refreshes it in place.

Observed 2026-09-02: rerun on a selected cluster made the paid call, then
500'd — the selected pool was read under the key `selected`, which is the
bool that says a selection was made, not the list. The fresh keywords were
left beside the cluster as a duplicate proposal."""
import os
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
from src import cluster_governance as cg, runs  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


RID = "test-rerun-run"
runs.save_run(RID, {
    "id": RID, "title": "t", "status": "done",
    "stages": [
        {"id": "intake", "label": "Intake", "status": "done", "artifact": {"locale": {"location_code": 2840, "language_code": "en"}}},
        {"id": "clusters", "label": "Clusters", "status": "done", "artifact": {
            "selected": True,
            "clusters": [{"cluster_name": "Core PM learning", "name": "Core PM learning", "head_term": "ai product manager course",
                          "keywords": ["ai product manager course", "ai pm course"], "selection_reason": "r"}],
            "discarded": [{"cluster_name": "Parked one", "name": "Parked one", "head_term": "pm interview prep",
                           "keywords": ["pm interview prep"], "discard_reason": "r"}],
        }},
    ],
})

fake = [{"keyword": "ai product manager course", "volume": 320, "difficulty": 20, "intent": "informational"},
        {"keyword": "ai product manager certification", "volume": 720, "difficulty": 24, "intent": "informational"},
        {"keyword": "ai pm course", "volume": 50, "difficulty": 10, "intent": "informational"}]

print("1. a selected cluster is refreshed in place")
with patch("src.tools.dataforseo.keyword_suggestions", lambda *a, **k: fake):
    res = cg.rerun_cluster_research(RID, "Core PM learning", by="webmcp")
ok(res.get("ok") is True, f"rerun succeeds: {res}")
ok(res["pool"] == "selected" and res["keywords_added"] == 1, f"one new keyword folded in: {res}")
run = runs.get_run(RID)
art = next(s["artifact"] for s in run["stages"] if s["id"] == "clusters")
ok(len(art["clusters"]) == 1, "no duplicate proposal left beside the cluster")
ok("ai product manager certification" in art["clusters"][0]["keywords"], "the fresh keyword is in the cluster")
ok(art["clusters"][0].get("refreshed") is True, "the cluster is marked refreshed")
ok(art["selected"] is True, "the selection flag is untouched")
log = run.get("governance") or []
ok(log and log[-1]["op"] == "rerun" and log[-1]["by"] == "webmcp", f"logged as a rerun by webmcp: {log[-1:] }")

print("2. a parked cluster is refreshed in its own pool")
with patch("src.tools.dataforseo.keyword_suggestions", lambda *a, **k: [{"keyword": "pm interview questions", "volume": 900, "difficulty": 30, "intent": "informational"}]):
    res = cg.rerun_cluster_research(RID, "Parked one")
ok(res.get("ok") is True and res["pool"] == "discarded", f"parked rerun succeeds: {res}")
art = next(s["artifact"] for s in runs.get_run(RID)["stages"] if s["id"] == "clusters")
ok(len(art["clusters"]) == 1 and len(art["discarded"]) == 1, "pools keep their sizes")
ok("pm interview questions" in art["discarded"][0]["keywords"], "the parked cluster got the keyword")

print("3. an unknown cluster is refused before any paid call")
called = []
with patch("src.tools.dataforseo.keyword_suggestions", lambda *a, **k: called.append(1) or []):
    res = cg.rerun_cluster_research(RID, "Nope")
ok(res.get("ok") is False and not called, "refused, nothing spent")

print(f"rerun: {PASS} assertions passed")
