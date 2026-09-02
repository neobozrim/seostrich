"""The brief's questions are questions people actually search for.

Before this, "the exact question this piece answers" was the model's guess
at intent. Now each selected cluster gets one People-also-ask lookup on its
head term; a piece for that cluster must take its question verbatim from
what Google shows, and the piece says so. Only a cluster Google shows
nothing for gets a written question, tagged as written."""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
from src import runs  # noqa: E402
from src.tools import strategy_brief as sb  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


RID = "test-paa-brief"
runs.save_run(RID, {
    "id": RID, "title": "Product Pirates Club", "status": "done",
    "stages": [
        {"id": "intake", "label": "Intake", "status": "done", "artifact": {"locale": {"location_code": 2826, "language_code": "en"}, "market": "UK-EN"}},
        {"id": "clusters", "label": "Clusters", "status": "done", "artifact": {
            "selected": True,
            "clusters": [
                {"cluster_name": "Core PM learning", "head_term": "ai product manager course",
                 "keywords": ["ai product manager course", "ai product manager certification"],
                 "keyword_stats": {"ai product manager course": {"volume": 320, "difficulty": 20}, "ai product manager certification": {"volume": 720, "difficulty": 24, "owned_by": ["maven.com"]}},
                 "metrics": {"total_volume": 1040, "avg_difficulty": 22}, "selection_reason": "demand"},
                {"cluster_name": "Eval practice", "head_term": "eval systems",
                 "keywords": ["eval systems"], "keyword_stats": {"eval systems": {"volume": 90, "difficulty": 8}},
                 "metrics": {"total_volume": 90, "avg_difficulty": 8}, "selection_reason": "fit"},
            ],
            "discarded": [{"cluster_name": "Parked", "discard_reason": "off-topic"}],
        }},
        {"id": "pillars", "label": "Pillars", "status": "done", "artifact": {"pillars": [{"pillar_title": "AI PM hub", "cluster_name": "Core PM learning", "priority": 1}]}},
    ],
})

calls = []


def fake_paa(term, location_code=2840, language_code="en"):
    calls.append((term, location_code, language_code))
    if term == "ai product manager course":
        return [{"question": "Is there a course for AI product managers?", "domain": "maven.com", "url": "https://maven.com/x"},
                {"question": "What does an AI product manager do?", "domain": "productschool.com", "url": ""}]
    return []  # Google shows nothing under "eval systems"


print("1. one lookup per selected cluster, in the run's market, and the questions reach the model")
inp = sb.build_input(runs.get_run(RID))
with patch.object(sb.dfs, "serp_paa", fake_paa):
    observed = sb.observe_questions(inp, RID, 2826, "en")
ok(calls[0] == ("ai product manager course", 2826, "en"), f"head term looked up in the run's market: {calls[0]}")
ok(observed == {"Core PM learning": 2, "Eval practice": 0}, f"observed counts: {observed}")
ok(inp["selected_clusters"][0]["observed_questions"][0]["answered_by"] == "maven.com", "who answers it today is kept")
ok([c[0] for c in calls] == ["ai product manager course", "eval systems"], f"empty head term falls back to the top keyword: {[c[0] for c in calls]}")

print("2. a paraphrase is rejected; the verbatim question passes")
piece = lambda q, cl="Core PM learning", tk="ai product manager certification": {"title": "T", "question": q, "cluster": cl, "target_keyword": tk, "format": "guide"}
base = {"the_call": {"pillar": "AI PM hub", "why": "w"}, "out_answer": [], "parked": [{"cluster": "Parked", "why": "off-topic"}]}
bad = dict(base, pieces=[piece("Which AI product manager course should I take?")])
ok(sb._valid(bad, inp)[0] is False and "observed_questions" in sb._valid(bad, inp)[1], "a made-up question for a cluster with observed ones is rejected")
good = dict(base, pieces=[piece("Is there a course for AI product managers?"), piece("what is an eval system", "Eval practice", "eval systems")])
ok(sb._valid(good, inp)[0] is True, f"verbatim (case/punctuation-insensitive) passes, written passes where nothing was observed: {sb._valid(good, inp)}")

dup = dict(base, pieces=[piece("Is there a course for AI product managers?"), piece("is there a course for ai product managers")])
ok(sb._valid(dup, inp)[0] is False and "same question" in sb._valid(dup, inp)[1], "two pieces on one question are rejected")

spread = dict(base, pieces=[piece("Is there a course for AI product managers?"), piece("What does an AI product manager do?")])
ok(sb._valid(spread, inp)[0] is False and "at least one piece" in sb._valid(spread, inp)[1], "a selected cluster with no piece is rejected")

print("3. provenance is decided by the match, not by what the model claims")
pcs = [dict(piece("is there a course for ai product managers?"), question_source="written"),
       dict(piece("what is an eval system", "Eval practice", "eval systems"), question_source="people_also_ask")]
sb._tag_questions(pcs, inp)
ok(pcs[0]["question_source"] == "people_also_ask" and pcs[0]["currently_answered_by"] == "maven.com" and pcs[0]["asked_under"] == "ai product manager course", f"observed piece tagged: {pcs[0]}")
ok(pcs[1]["question_source"] == "written" and "currently_answered_by" not in pcs[1], f"written piece tagged written: {pcs[1]}")

print("4. write_brief records the observation on the artefact; a lookup failure fails open")
answers = [dict(good)]
serp_calls = []
def fake_serp(q, location_code=2840, language_code="en", depth=10):
    serp_calls.append(q)
    return [{"domain": "www.productschool.com", "url": "https://www.productschool.com/x", "rank": 1}]
with patch.object(sb.dfs, "serp_paa", fake_paa), patch.object(sb.dfs, "serp_organic", fake_serp), patch.object(sb.llm, "chat", lambda *a, **k: "x"), patch.object(sb.llm, "parse_json_response", lambda r: answers.pop(0)):
    res = sb.write_brief(RID)
ok(res["ok"] is True, f"brief written: {res.get('error')}")
ok(serp_calls == ["what is an eval system"], f"one SERP per piece that lacks an answerer (the PAA one already had maven.com): {serp_calls}")
ok(res["brief"]["pieces"][1]["currently_answered_by"] == "productschool.com" and res["brief"]["pieces"][1]["answered_by_source"] == "serp", "the top organic result is who answers it today")
art = next(s["artifact"] for s in runs.get_run(RID)["stages"] if s["id"] == "brief")
ok(art["based_on"]["questions_observed"] == {"Core PM learning": 2, "Eval practice": 0}, f"observation recorded: {art['based_on']}")
ok(art["pieces"][0]["question_source"] == "people_also_ask" and art["pieces"][1]["question_source"] == "written", "pieces carry their source")

def boom(*a, **k):
    raise RuntimeError("budget exhausted")
answers = [dict(base, pieces=[piece("Anything the model likes?")])]
with patch.object(sb.dfs, "serp_paa", boom), patch.object(sb.dfs, "serp_organic", boom), patch.object(sb.llm, "chat", lambda *a, **k: "x"), patch.object(sb.llm, "parse_json_response", lambda r: answers.pop(0)):
    res = sb.write_brief(RID)
ok(res["ok"] is True and res["brief"]["pieces"][0]["question_source"] == "written", "no lookup → the brief is still written, questions tagged written")

print(f"paa-questions: {PASS} assertions passed")
