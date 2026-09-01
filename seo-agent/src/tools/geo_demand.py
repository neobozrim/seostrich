"""GEO demand graph — search demand, then AI citability, then the real questions.

The node order matters and is enforced in code:

  1. market gate        — country + language must be user-confirmed
  2. search demand      — keyword_overview: real volume / difficulty / CPC
  3. AI citability      — ai_mentions_keywords: is this something ChatGPT and
                          Google AI actually answer, who do they cite, and how
                          much of the answer space is unclaimed
  4. pick the winners   — deterministic ranking over the two measurements above
  5. real questions     — serp_paa, but ONLY on the winners

Step 5 is why the order is enforced. People-also-ask costs one SERP call per
term, so asking it about everything is how a run burns its budget on topics
that turned out to have neither search demand nor AI presence. Measuring first
and harvesting questions only for terms that earned it is the whole point.

Everything here is measured. No model estimates any number; the ranking rule is
arithmetic and publishes its own inputs so a reader can re-rank differently.
"""
from __future__ import annotations

from collections import Counter

from .. import market as market_mod
from .. import pipeline_recorder as rec
from .dataforseo import ai_mentions_keywords, budget_remaining, keyword_overview, serp_paa

# One SERP call per term, so the harvest is capped.
MAX_QUESTION_TERMS = 4
# search_mentions takes at most 10 terms per call.
MAX_TERMS = 10


def _demand_rows(topics: list[str], location_code: int, language_code: str) -> list[dict]:
    """Real search volume / difficulty / CPC per topic (1 DataForSEO call)."""
    try:
        rows = keyword_overview(topics, location_code=location_code, language_code=language_code)
    except Exception as exc:
        print(f"[geo_demand] keyword_overview failed: {exc}")
        rows = []
    by_kw = {str(r.get("keyword", "")).lower(): r for r in rows if isinstance(r, dict)}
    # Keep every requested topic, even those the API has no data for: a topic
    # with no search volume can still be worth writing if AI engines answer it.
    return [
        by_kw.get(t.lower(), {"keyword": t, "volume": 0, "difficulty": 0, "cpc": 0, "intent": ""})
        for t in topics
    ]


def _citability(topics: list[str], location_code: int, language_code: str) -> dict[str, dict]:
    """Per-topic AI presence: answered questions, AI volume, who gets cited."""
    try:
        mentions = ai_mentions_keywords(topics, location_code=location_code, language_code=language_code)
    except Exception as exc:
        print(f"[geo_demand] ai_mentions_keywords failed: {exc}")
        mentions = []

    per_topic: dict[str, dict] = {
        t: {"questions": [], "ai_search_volume": 0, "answered": 0, "sources": Counter()}
        for t in topics
    }
    for item in mentions:
        question = (item.get("question") or "").lower()
        # Attribute to the topic sharing the most significant words.
        best, best_hits = None, 0
        for topic in topics:
            words = [w for w in topic.lower().split() if len(w) > 2]
            hits = sum(1 for w in words if w in question)
            if hits > best_hits:
                best, best_hits = topic, hits
        if best is None:
            continue
        bucket = per_topic[best]
        bucket["questions"].append({
            "question": item.get("question", ""),
            "platform": item.get("platform", ""),
            "has_answer": item.get("has_answer", False),
            "answer_snippet": item.get("answer_snippet", ""),
            "sources": item.get("sources", []),
        })
        bucket["ai_search_volume"] += item.get("ai_search_volume") or 0
        if item.get("has_answer"):
            bucket["answered"] += 1
        for source in item.get("sources") or []:
            if source.get("domain"):
                bucket["sources"][source["domain"]] += 1

    out = {}
    for topic, bucket in per_topic.items():
        total = len(bucket["questions"])
        answered = bucket["answered"]
        out[topic] = {
            "ai_questions_found": total,
            "ai_search_volume": bucket["ai_search_volume"],
            "answered_share": round(answered / total, 2) if total else 0.0,
            # What no engine answers well yet is what you can win.
            "open_share": round((total - answered) / total, 2) if total else 0.0,
            "cited_sources": [
                {"domain": d, "citations": n} for d, n in bucket["sources"].most_common(5)
            ],
            "questions": bucket["questions"][:10],
        }
    return out


def _rank(demand: list[dict], citability: dict[str, dict]) -> list[dict]:
    """Order topics by measured evidence. Arithmetic, and it shows its work."""
    ranked = []
    for row in demand:
        topic = row.get("keyword", "")
        geo = citability.get(topic, {})
        volume = row.get("volume") or 0
        ai_questions = geo.get("ai_questions_found", 0)
        ai_volume = geo.get("ai_search_volume", 0)
        open_share = geo.get("open_share", 0.0)

        if ai_questions and volume:
            basis = "AI engines answer this AND it has search volume"
        elif ai_questions:
            basis = "AI engines answer this, but there is little classic search volume"
        elif volume:
            basis = "classic search volume, but no AI answers captured yet"
        else:
            basis = "no measured demand in either channel"

        ranked.append({
            "topic": topic,
            "search_volume": volume,
            "difficulty": row.get("difficulty") or 0,
            "cpc": row.get("cpc") or 0,
            "intent": row.get("intent") or "",
            "ai_questions_found": ai_questions,
            "ai_search_volume": ai_volume,
            "answered_share": geo.get("answered_share", 0.0),
            "open_share": open_share,
            "cited_sources": geo.get("cited_sources", []),
            "evidence": basis,
        })

    # AI presence first (this is a GEO flow), then classic volume, then how much
    # of the answer space is still unclaimed.
    ranked.sort(
        key=lambda r: (r["ai_questions_found"], r["search_volume"], r["open_share"]),
        reverse=True,
    )
    return ranked


def run_geo_demand(
    topics: list[str],
    location_code: int | None = None,
    language_code: str | None = None,
    max_question_terms: int = MAX_QUESTION_TERMS,
) -> dict:
    """Run the GEO demand graph inside the active pipeline run."""
    if not rec.active_run_id():
        return {"success": False, "error": "run_geo_demand must run inside a pipeline run"}

    clean = [t.strip() for t in (topics or []) if isinstance(t, str) and t.strip()][:MAX_TERMS]
    if not clean:
        return {"success": False, "error": "topics is required (list of head terms)"}

    try:
        market = market_mod.require_market(location_code, language_code)
    except market_mod.MarketNotConfirmed as exc:
        return {"success": False, "error": str(exc), "needs": "confirm_market"}
    loc, lang = market["location_code"], market["language_code"]
    rec.log_activity("step", detail=f"market: {market['label']}")

    steps: list[str] = []

    rec.log_activity("step", detail=f"node: search demand for {len(clean)} topics")
    demand = _demand_rows(clean, loc, lang)
    rec.record_tool("keyword_overview", {"location_code": loc, "language_code": lang},
                    demand, True)
    steps.append("demand")

    rec.log_activity("step", detail="node: AI citability (who answers, who is cited)")
    citability = _citability(clean, loc, lang)
    steps.append("citability")

    rec.log_activity("step", detail="node: rank topics on measured demand")
    ranked = _rank(demand, citability)
    steps.append("ranked")

    # Harvest questions only where the evidence justifies a SERP call.
    winners = [r for r in ranked if r["ai_questions_found"] or r["search_volume"]]
    winners = winners[:max_question_terms] or ranked[:1]
    skipped = [r["topic"] for r in ranked if r not in winners]

    rec.log_activity(
        "step",
        detail=f"node: People-also-ask for the top {len(winners)} "
               f"(skipping {len(skipped)} with no measured demand)",
    )
    questions: dict[str, list[dict]] = {}
    for row in winners:
        if budget_remaining() <= 0:
            rec.log_activity("step", detail="budget exhausted — stopping the question harvest")
            break
        try:
            questions[row["topic"]] = serp_paa(row["topic"], location_code=loc, language_code=lang)
        except Exception as exc:
            questions[row["topic"]] = []
            print(f"[geo_demand] PAA failed for {row['topic']!r}: {exc}")
    steps.append("questions")

    brief = []
    for row in winners:
        paa = questions.get(row["topic"], [])
        ai_questions = citability.get(row["topic"], {}).get("questions", [])
        brief.append({
            "topic": row["topic"],
            "why_this_topic": row["evidence"],
            "metrics": {
                "search_volume": row["search_volume"],
                "difficulty": row["difficulty"],
                "cpc": row["cpc"],
                "intent": row["intent"],
                "ai_questions_found": row["ai_questions_found"],
                "ai_search_volume": row["ai_search_volume"],
                "answered_share": row["answered_share"],
                "open_share": row["open_share"],
            },
            "currently_cited": row["cited_sources"],
            "questions_people_ask": [q.get("question") for q in paa][:10],
            "questions_ai_answers": [q.get("question") for q in ai_questions][:10],
        })

    result = {
        "success": True,
        "market": market["label"],
        "topics_examined": clean,
        "ranked": ranked,
        "brief": brief,
        "skipped_no_demand": skipped,
        "steps": steps,
        "method": (
            "Search volume and AI presence are measured from DataForSEO; the "
            "ranking is arithmetic over those measurements and publishes its "
            "inputs. People-also-ask was fetched only for topics that showed "
            "demand, because it costs one SERP call per topic."
        ),
    }
    rec.record_deliverable("ai_citability", "GEO demand brief", result)
    rec.log_activity("step", detail="graph complete")
    return result
