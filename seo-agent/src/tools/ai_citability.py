"""AI-citability brief — how AI engines answer questions around your head terms.

Deterministic assembly (no LLM judgment): one DataForSEO search_mentions
call covering all head terms (keyword-targeted) + one SERP-advanced call
per head term for People-also-ask. Produces an answer-first brief:

- ai_demand: how many questions AI engines are answering on the topic + AI search volume
- has_answers: share of captured questions that got a real answer
- cited_sources: the domains AI engines currently cite (who you'd displace)
- questions: the questions themselves (answer-first content targets)
- paa: Google's People-also-ask for the same head terms

Recorded as the `ai_citability` stage of the active run.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ..tools.dataforseo import ai_mentions_keywords, serp_paa


def ai_citability_brief(
    head_terms: list[str],
    location_code: int = 2840,
    language_code: str = "en",
) -> dict:
    """Build the AI-citability brief for up to 6 head terms."""
    terms = [t.strip() for t in (head_terms or []) if isinstance(t, str) and t.strip()][:6]
    if not terms:
        return {"success": False, "error": "head_terms is required (list of up to 6)"}

    try:
        mentions = ai_mentions_keywords(terms, location_code=location_code, language_code=language_code)
    except Exception as e:
        return {"success": False, "error": f"AI mentions lookup failed: {e}"}

    # Per-term PAA (one SERP call each — bounded by the 6-term cap)
    paa_by_term: dict[str, list[dict]] = {}
    for term in terms:
        try:
            paa_by_term[term] = serp_paa(term, location_code=location_code, language_code=language_code)
        except Exception as e:
            paa_by_term[term] = []
            print(f"[ai_citability] PAA failed for '{term}': {e}")

    # Attribute mention items to the best-matching head term
    per_term: dict[str, list[dict]] = {t: [] for t in terms}
    for item in mentions:
        q = (item.get("question") or "").lower()
        best = None
        for term in terms:
            words = [w for w in term.lower().split() if len(w) > 2]
            if words and any(w in q for w in words):
                best = term
                break
        per_term[best or terms[0]].append(item)

    cited = Counter(
        s["domain"] for item in mentions for s in item.get("sources", []) if s.get("domain")
    )

    term_briefs = []
    for term in terms:
        items = per_term.get(term, [])
        answered = [i for i in items if i.get("has_answer")]
        volumes = [i.get("ai_search_volume") or 0 for i in items]
        term_briefs.append({
            "head_term": term,
            "questions_asked": len(items),
            "ai_search_volume": sum(volumes),
            "answer_share": round(len(answered) / len(items), 2) if items else 0,
            "top_questions": [i["question"] for i in items if i.get("question")][:8],
            "top_cited_sources": [d for d, _ in Counter(
                s["domain"] for i in items for s in i.get("sources", []) if s.get("domain")
            ).most_common(5)],
            "paa": [p["question"] for p in paa_by_term.get(term, [])][:8],
        })

    brief = {
        "market": f"{location_code}-{language_code}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head_terms": term_briefs,
        "questions_captured": len(mentions),
        "overall_answer_share": (
            round(sum(1 for i in mentions if i.get("has_answer")) / len(mentions), 2)
            if mentions else 0
        ),
        "top_cited_sources": [{"domain": d, "mentions": n} for d, n in cited.most_common(10)],
    }
    return {"success": True, "brief": brief}
