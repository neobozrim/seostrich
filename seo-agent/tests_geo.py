"""The GEO graph: measure demand, check AI citability, THEN harvest questions.

Order matters for cost. People-also-ask is one SERP call per topic, so asking
it about everything spends the budget on topics with no demand. This asserts
the gate holds.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import market as market_mod
from src import pipeline_recorder as rec
from src import runs
from src.tools import geo_demand as gd

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


TOPICS = ["agentic commerce", "knowledge graphs", "llm evaluation", "dead topic"]
paa_calls: list[str] = []


def fake_keyword_overview(keywords, location_code=2840, language_code="en"):
    data = {"agentic commerce": 320, "knowledge graphs": 90, "llm evaluation": 0, "dead topic": 0}
    return [{"keyword": k, "volume": data.get(k, 0), "difficulty": 12, "cpc": 2.5,
             "intent": "informational"} for k in keywords]


mention_calls: list[str] = []


def fake_ai_mentions(keywords, location_code=2840, language_code="en", limit=100):
    mention_calls.extend(keywords)
    return [
        {"question": "what is agentic commerce", "platform": "chatgpt", "has_answer": True,
         "answer_snippet": "…", "ai_search_volume": 40,
         "sources": [{"domain": "stripe.com", "url": "u", "title": "t"},
                     {"domain": "tinyblog.dev", "url": "u", "title": "t"}]},
        {"question": "how do agentic commerce payments work", "platform": "google", "has_answer": False,
         "answer_snippet": "", "ai_search_volume": 10, "sources": []},
        {"question": "how are knowledge graphs built", "platform": "chatgpt", "has_answer": True,
         "answer_snippet": "…", "ai_search_volume": 25,
         "sources": [{"domain": "neo4j.com", "url": "u", "title": "t"}]},
        {"question": "llm evaluation frameworks compared", "platform": "chatgpt", "has_answer": False,
         "answer_snippet": "", "ai_search_volume": 5, "sources": []},
    ]


def fake_serp_paa(keyword, location_code=2840, language_code="en"):
    paa_calls.append(keyword)
    return [{"question": f"real question about {keyword}", "domain": "d", "url": "u"}]


gd.keyword_overview = fake_keyword_overview
gd.ai_mentions_keywords = fake_ai_mentions
gd.serp_paa = fake_serp_paa
gd.budget_remaining = lambda *a, **k: 99
# stripe/mastercard-tier vs a niche site, so displaceability has something to judge
gd.bulk_domain_ranks = lambda doms: {
    "stripe.com": 729, "neo4j.com": 520, "tinyblog.dev": 180,
}

RID = "test-geo-run"
runs.save_run(RID, {"id": RID, "project": "T", "title": "geo", "status": "running", "stages": []})

print("1. the market gate applies here too")
with rec.use_run(RID):
    market_mod.reset(RID)
    r = gd.run_geo_demand(TOPICS)
    chk("refused without a confirmed market",
        r.get("success") is False and r.get("needs") == "confirm_market", str(r)[:100])
    market_mod.confirm_market("US", "en", run_id=RID)

print("2. the graph runs in order and records its steps")
with rec.use_run(RID):
    res = gd.run_geo_demand(TOPICS, max_question_terms=2)
chk("succeeded", res.get("success") is True, str(res)[:120])
chk("steps in order",
    res["steps"] == ["demand", "shortlist", "citability", "displaceability",
                     "ranked", "questions"],
    str(res["steps"]))
chk("market recorded", res["market"] == "US-EN")

print("3. the EXPENSIVE call is gated by the cheap one")
# search_mentions is ~$0.10 per keyword; a topic the free volume check already
# showed is dead must never reach it.
chk("dead topic never sent to the paid call",
    "dead topic" not in mention_calls, str(mention_calls))
chk("only shortlisted topics were charged for",
    set(mention_calls) <= {"agentic commerce", "knowledge graphs"}, str(mention_calls))
chk("and it is reported, not silently dropped",
    "dead topic" in res["not_sent_to_paid_call"], str(res["not_sent_to_paid_call"]))
chk("llm evaluation (zero volume) also skipped",
    "llm evaluation" in res["not_sent_to_paid_call"], str(res["not_sent_to_paid_call"]))
chk("cost is stated back to the caller",
    "search_mentions" in res["cost_note"], res["cost_note"])

print("3b. PAA runs only on the winners")
chk("2 SERP calls, not 4", len(paa_calls) == 2, str(paa_calls))
chk("no PAA for the dead topic", "dead topic" not in paa_calls, str(paa_calls))

print("4. ranking prefers AI presence, then volume")
ranked = res["ranked"]
chk("agentic commerce ranks first",
    ranked[0]["topic"] == "agentic commerce", ranked[0]["topic"])
chk("only measured topics are ranked", len(ranked) == 2, str([r["topic"] for r in ranked]))
chk("dead topic absent from the ranking",
    all(r["topic"] != "dead topic" for r in ranked), str(ranked))
chk("every row states its evidence", all(r["evidence"] for r in ranked))
chk("evidence names both channels",
    "AI engines answer this" in ranked[0]["evidence"], ranked[0]["evidence"])

print("5. the brief carries both question sources and the citation picture")
top = res["brief"][0]
chk("topic named", top["topic"] == "agentic commerce")
chk("says why it was chosen", bool(top["why_this_topic"]))
chk("real PAA questions", top["questions_people_ask"] == ["real question about agentic commerce"])
chk("questions AI already answers", "what is agentic commerce" in top["questions_ai_answers"])
chk("who is cited today", top["currently_cited"][0]["domain"] == "stripe.com",
    str(top["currently_cited"]))
chk("open share computed", top["metrics"]["open_share"] == 0.5, str(top["metrics"]["open_share"]))
chk("answered share computed", top["metrics"]["answered_share"] == 0.5)
chk("search volume carried", top["metrics"]["search_volume"] == 320)
chk("method states what was measured", "measured" in res["method"])

print("6. displaceability: can a small site win this topic?")
top = res["brief"][0]
chk("verdict present", bool(top["can_you_displace_them"]), str(top)[:80])
chk("a niche citation makes it winnable",
    "winnable" in top["can_you_displace_them"], top["can_you_displace_them"])
chk("names the niche site",
    any(d["domain"] == "tinyblog.dev" for d in top["niche_sites_already_cited"]),
    str(top["niche_sites_already_cited"]))
chk("giant not counted as niche",
    all(d["domain"] != "stripe.com" for d in top["niche_sites_already_cited"]))
chk("authority range reported",
    top["metrics"]["strongest_cited_authority"] == 729
    and top["metrics"]["weakest_cited_authority"] == 180,
    str(top["metrics"]))
kg = next(b for b in res["brief"] if b["topic"] == "knowledge graphs")
chk("giants-only topic marked hard, not winnable",
    "winnable" not in kg["can_you_displace_them"], kg["can_you_displace_them"])

print("7. recorded as an inspectable stage")
run = runs.get_run(RID)
stage_ids = [s["id"] for s in run.get("stages", [])]
chk("ai_citability stage exists", "ai_citability" in stage_ids, str(stage_ids))

print("8. degrades safely")
with rec.use_run(RID):
    chk("no topics rejected", gd.run_geo_demand([]).get("success") is False)
chk("outside a run rejected", gd.run_geo_demand(TOPICS).get("success") is False)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
