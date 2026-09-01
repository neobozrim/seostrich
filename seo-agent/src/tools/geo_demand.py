"""GEO demand graph — narrow cheaply, then pay for the expensive signal.

Node order is enforced in code, and the order is a cost decision:

  1. market gate      — country + language, user-confirmed
  2. search demand    — keyword_overview: ONE cheap call covering every
                        candidate, giving real volume / difficulty / CPC
  3. shortlist        — keep the candidates with demand, drop the rest
  4. AI citability    — search_mentions, ONE CALL PER KEYWORD at ~$0.10 each
                        (DataForSEO's own example shows cost 0.101), so it runs
                        only on the shortlist. Returns what AI engines answer,
                        the answer text itself, and which domains it cites.
  5. displaceability  — bulk_domain_ranks: ONE call grading every cited domain.
                        This is what decides whether a small site can win the
                        topic. "Is it answered" is not the signal — Google AI
                        Overview answered 42 of 42 questions on a measured
                        topic. Whether a NICHE site is already cited is.
  6. real questions   — People-also-ask, cheap, on the final few winners.

On ai_search_volume, from DataForSEO's own documentation: for Google AI
Overviews it is DERIVED FROM Google search volume, and a topic's figure is the
SUM across every matched question. It is therefore a measure of the size of the
question cluster, NOT a separate AI demand channel, and it must not be compared
against a single head term's volume. For ChatGPT it is computed differently
again (from People-also-ask counts), so cross-platform comparison is invalid.

Everything here is measured. No model estimates any number; the ranking is
arithmetic and publishes its own inputs so a reader can re-rank differently.
"""
from __future__ import annotations

from collections import Counter

from .. import market as market_mod
from .. import pipeline_recorder as rec
from .run_sections import write_full_result
from .dataforseo import (
    ai_mentions_keywords, budget_remaining, bulk_domain_ranks,
    keyword_overview, serp_paa,
)

# People-also-ask is cheap but still one SERP call per term.
MAX_QUESTION_TERMS = 4
# search_mentions is the expensive call (~$0.10 each, one per keyword), so the
# shortlist that reaches it is bounded separately and more tightly.
MAX_MENTION_TERMS = 6
# Cap on topics per run: search_mentions is one call PER topic (the endpoint
# intersects batched targets rather than unioning them), so this bounds cost.
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
    rows_out = []
    for topic in topics:
        row = dict(by_kw.get(topic.lower(),
                             {"volume": 0, "difficulty": 0, "cpc": 0, "intent": ""}))
        # Always key by the caller's own string. The API echoes its own
        # normalised form, and every downstream lookup (citability,
        # displaceability) is keyed by what the caller asked for — a silent
        # mismatch there zeroes a topic that actually had data.
        row["keyword"] = topic
        rows_out.append(row)
    return rows_out


def _citability(
    topics: list[str],
    location_code: int,
    language_code: str,
    wide: bool = True,
) -> dict[str, dict]:
    """Per-topic AI presence: answered questions, AI volume, who gets cited.

    Two passes, because the two scopes answer different questions:

      question scope — the user's question contains the term. Tight and
        on-topic: these are the questions worth writing against.
      answer scope   — the AI's ANSWER contains the term, whatever the question
        was. Far broader (3,504 matches vs 29 on a measured topic, 88 distinct
        cited domains vs 48) because it catches adjacent questions that never
        name the term. Those extra domains are the real competitive set — the
        sites getting cited on this subject even when nobody asked about it by
        name.

    The wide pass doubles the paid call per topic, so it is a flag. It only
    contributes to the citation picture; the questions in the brief still come
    from the tight pass, so a broad match cannot pollute what gets written.
    """
    try:
        mentions = ai_mentions_keywords(
            topics, location_code=location_code, language_code=language_code,
            scope="question",
        )
    except Exception as exc:
        print(f"[geo_demand] ai_mentions_keywords(question) failed: {exc}")
        mentions = []

    wide_mentions: list[dict] = []
    if wide:
        try:
            wide_mentions = ai_mentions_keywords(
                topics, location_code=location_code, language_code=language_code,
                scope="answer",
            )
        except Exception as exc:
            print(f"[geo_demand] ai_mentions_keywords(answer) failed: {exc}")

    per_topic: dict[str, dict] = {
        t: {"questions": [], "ai_search_volume": 0, "answered": 0, "sources": Counter()}
        for t in topics
    }
    for item in mentions:
        # The API is queried one topic at a time, so each row knows which topic
        # it answered. Fall back to word overlap only for older payloads.
        best = item.get("matched_keyword")
        if best not in per_topic:
            question = (item.get("question") or "").lower()
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

    # The wide pass contributes DOMAINS ONLY. Its questions are deliberately
    # kept out of the brief: they matched on answer text, so they are about the
    # subject but often not about the topic as asked.
    wide_sources: dict[str, Counter] = {t: Counter() for t in topics}
    wide_seen: dict[str, int] = {t: 0 for t in topics}
    for item in wide_mentions:
        topic = item.get("matched_keyword")
        if topic not in wide_sources:
            continue
        wide_seen[topic] += 1
        for source in item.get("sources") or []:
            if source.get("domain"):
                wide_sources[topic][source["domain"]] += 1

    out = {}
    for topic, bucket in per_topic.items():
        total = len(bucket["questions"])
        answered = bucket["answered"]
        out[topic] = {
            "ai_questions_found": total,
            # SUM across matched questions, and for Google AI Overviews it is
            # derived from Google search volume — so it sizes the question
            # cluster, and must NOT be compared against a head term's volume.
            "ai_search_volume_sum": bucket["ai_search_volume"],
            "ai_search_volume": bucket["ai_search_volume"],
            "answered_share": round(answered / total, 2) if total else 0.0,
            # What no engine answers well yet is what you can win.
            "open_share": round((total - answered) / total, 2) if total else 0.0,
            "cited_sources": [
                {"domain": d, "citations": n} for d, n in bucket["sources"].most_common(5)
            ],
            # Union of both passes: the widest honest view of who holds this
            # subject, used for the displaceability verdict.
            # Each domain carries WHICH pass found it. A domain cited on a
            # question that names the topic is on-topic by construction; one
            # found only by matching the answer text is adjacent and may be
            # drift (the answer-scope pass repeatedly surfaces
            # thehungergames.fandom.com for "forward deployed engineer"). The
            # noise cannot be filtered away reliably, so it is LABELLED and the
            # reader — or a WebMCP agent — decides.
            "competitive_domains": [
                {
                    "domain": d,
                    "citations": n,
                    "found_by": (
                        "asked_about_this_topic" if bucket["sources"].get(d)
                        else "mentioned_in_adjacent_answers"
                    ),
                    "confidence": "high" if bucket["sources"].get(d) else "needs_review",
                }
                for d, n in (bucket["sources"] + wide_sources[topic]).most_common(15)
            ],
            "wide_answers_scanned": wide_seen[topic],
            "questions": bucket["questions"][:10],
        }
    return out


# Backlink authority rank runs 0-1000. A site under this is one a small,
# focused publisher can realistically out-rank on a specific question.
NICHE_AUTHORITY_MAX = 350
# Above this a domain is a global brand or major publisher: being cited
# alongside them is possible, displacing them is not.
GIANT_AUTHORITY_MIN = 600


def _displaceability(citability: dict[str, dict]) -> dict[str, dict]:
    """Grade the domains AI engines cite, in ONE extra DataForSEO call.

    Answers the question a strategy actually turns on: are the incumbents
    displaceable? A topic whose answers cite only Mastercard, Stripe and
    McKinsey is closed to a new site no matter how much AI demand it has. A
    topic where a niche site already appears is open.
    """
    domains = {
        src["domain"]
        for geo in citability.values()
        for src in (geo.get("competitive_domains") or geo.get("cited_sources", []))
        if src.get("domain")
    }
    ranks = bulk_domain_ranks(sorted(domains)) if domains else {}

    out: dict[str, dict] = {}
    for topic, geo in citability.items():
        graded = []
        for src in (geo.get("competitive_domains") or geo.get("cited_sources", [])):
            rank = ranks.get(str(src.get("domain", "")).lower(), 0)
            # `citations` comes through from the counter; the >1 filter below
            # depends on it, so assert its presence rather than defaulting to 0
            # and silently disqualifying everything.
            graded.append({**src, "authority_rank": rank,
                           "citations": src.get("citations", 0)})
        graded.sort(key=lambda d: d["authority_rank"], reverse=True)

        # A niche site must be cited MORE THAN ONCE to count toward the verdict.
        # The wide answer-scope pass matches on answer text, so a single stray
        # hit is common — "forward deployed engineer" pulled in a Hunger Games
        # fan wiki. One appearance is noise; repeat citation is a pattern.
        niche = [
            d for d in graded
            if 0 < d["authority_rank"] <= NICHE_AUTHORITY_MAX
            and (d.get("citations") or 0) > 1
        ]
        # Niche sites found on questions that actually name the topic are the
        # trustworthy evidence; the rest are worth reading but not betting on.
        niche_confirmed = [d for d in niche if d.get("confidence") == "high"]
        niche_review = [d for d in niche if d.get("confidence") != "high"]
        niche_single_hit = [
            d for d in graded
            if 0 < d["authority_rank"] <= NICHE_AUTHORITY_MAX
            and (d.get("citations") or 0) <= 1
        ]
        giants = [d for d in graded if d["authority_rank"] >= GIANT_AUTHORITY_MIN]

        if not graded:
            verdict = "no citation data — cannot judge the competition yet"
        elif niche_confirmed:
            verdict = (
                f"winnable: {len(niche_confirmed)} niche site(s) are cited on "
                f"questions that name this topic (weakest "
                f"{min(d['authority_rank'] for d in niche_confirmed)}), so it does "
                f"not require a global brand to be quoted"
            )
        elif niche:
            verdict = (
                f"probably winnable, but verify: {len(niche)} niche site(s) appear, "
                f"only in answers to ADJACENT questions rather than to this topic "
                f"by name — check they are really about your subject before "
                f"betting on it"
            )
        elif niche_single_hit:
            verdict = (
                f"uncertain: {len(niche_single_hit)} niche site(s) appear, but each "
                f"only once, which is as likely to be a stray match as a real "
                f"opening — check them before betting on this topic"
            )
        elif giants:
            verdict = (
                f"hard: every cited source is a high-authority site "
                f"(top {giants[0]['authority_rank']}), so expect to be quoted "
                f"only alongside them, not instead of them"
            )
        else:
            verdict = "mid-authority sites hold the citations; contestable with depth"

        out[topic] = {
            "cited_sources": graded,
            "niche_sites_cited": niche,
            "niche_sites_confirmed_on_topic": niche_confirmed,
            "niche_sites_needing_review": niche_review,
            "confidence": "high" if niche_confirmed else ("low" if niche else "n/a"),
            # Surfaced separately so the reader can judge rather than being
            # silently excluded — a single citation may still be a real signal.
            "niche_sites_cited_once": niche_single_hit,
            "distinct_domains": len(graded),
            # Rank 0 means the backlink API had no data for that domain, not
            # "weakest site on earth" — it is already excluded from `niche`, so
            # it must not set the floor here either.
            "weakest_cited_authority": min(
                (d["authority_rank"] for d in graded if d["authority_rank"] > 0), default=0
            ),
            "strongest_cited_authority": max((d["authority_rank"] for d in graded), default=0),
            "unranked_domains": sum(1 for d in graded if d["authority_rank"] == 0),
            "displaceability": verdict,
        }
    return out


def _rank(demand: list[dict], citability: dict[str, dict],
          competition: dict[str, dict] | None = None) -> list[dict]:
    """Order topics by measured evidence. Arithmetic, and it shows its work."""
    ranked = []
    for row in demand:
        topic = row.get("keyword", "")
        geo = citability.get(topic, {})
        comp = (competition or {}).get(topic, {})
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
            "cited_sources": comp.get("cited_sources") or geo.get("cited_sources", []),
            "niche_sites_cited": comp.get("niche_sites_cited", []),
            "weakest_cited_authority": comp.get("weakest_cited_authority", 0),
            "strongest_cited_authority": comp.get("strongest_cited_authority", 0),
            "displaceability": comp.get("displaceability", ""),
            "evidence": basis,
        })

    # AI presence first (this is a GEO flow), then classic volume, then how much
    # of the answer space is still unclaimed.
    # Winnable topics first. A topic whose citations are all high-authority is
    # worth less to a small publisher than a slightly smaller one where a niche
    # site is already quoted, however much AI demand the former has.
    ranked.sort(
        key=lambda r: (
            bool(r["niche_sites_cited"]),
            r["ai_questions_found"],
            r["search_volume"],
        ),
        reverse=True,
    )
    return ranked


def _content_plan(row: dict, paa: list[dict], ai_questions: list[dict]) -> list[dict]:
    """Turn the measured questions into sections someone can actually write.

    The technique GEO rewards is answer-first: the question becomes the
    heading, and the first two sentences under it ARE the answer, so a
    generative engine can lift that passage and cite it. A post that opens with
    "here is my journey with evals" gives an engine nothing quotable.

    Each section therefore carries the exact question, where it came from, and
    who currently gets cited for it — the page you would have to out-answer.
    """
    sections = []
    seen: set[str] = set()

    # People-also-ask first: these are full sentences real users type, which
    # makes them better headings than the fragments the AI-mention rows carry.
    for entry in paa:
        question = (entry.get("question") or "").strip()
        key = question.lower()
        if not question or key in seen:
            continue
        seen.add(key)
        sections.append({
            "heading": question,
            "source": "people_also_ask",
            "answer_first_brief": (
                f"Open the section by answering \"{question}\" in one or two "
                f"plain sentences, then add the depth underneath."
            ),
            "currently_answered_by": entry.get("domain") or "",
        })

    for entry in ai_questions:
        question = (entry.get("question") or "").strip()
        key = question.lower()
        if not question or key in seen:
            continue
        seen.add(key)
        cited = [src.get("domain") for src in (entry.get("sources") or []) if src.get("domain")]
        sections.append({
            "heading": question,
            "source": "ai_engine_answered_this",
            "answer_first_brief": (
                f"An AI engine already answers \"{question}\". Give a better, "
                f"more specific answer in the first two sentences."
            ),
            "currently_cited": cited[:3],
        })

    return sections[:12]


def _previous_result() -> dict | None:
    """The GEO brief already recorded on this run, if any."""
    from .. import runs as runs_store

    run_id = rec.active_run_id()
    if not run_id:
        return None
    run = runs_store.get_run(run_id)
    for stage in (run or {}).get("stages", []):
        if stage.get("id") == "ai_citability":
            artifact = stage.get("artifact") or {}
            inner = artifact.get("artifact") if isinstance(artifact.get("artifact"), dict) else artifact
            if inner.get("brief"):
                return inner
    return None


def _handoff(result: dict) -> dict:
    """Persist the full brief, hand back a manifest plus the headline numbers.

    See run_sections: the agent reads what it decides it needs. A projection
    that pre-selects fields hides whatever the chooser did not think of, which
    is the opposite of useful when the agent is the one doing the judging.
    """
    run_id = rec.active_run_id() or ""
    manifest = write_full_result(run_id, "geo_demand", result)
    topics = [
        {
            "topic": e.get("topic"),
            "search_volume": (e.get("metrics") or {}).get("search_volume"),
            "ai_questions_found": (e.get("metrics") or {}).get("ai_questions_found"),
            "cited_authority_range": [
                (e.get("metrics") or {}).get("weakest_cited_authority"),
                (e.get("metrics") or {}).get("strongest_cited_authority"),
            ],
            "verdict": e.get("can_you_displace_them"),
            "sections_to_write": len(e.get("content_plan") or []),
        }
        for e in result.get("brief", [])
    ]
    return {
        "success": result.get("success"),
        "market": result.get("market"),
        "steps": result.get("steps"),
        "topics": topics,
        "skipped_no_demand": result.get("skipped_no_demand"),
        "not_sent_to_paid_call": result.get("not_sent_to_paid_call"),
        "cost_note": result.get("cost_note"),
        "reading_the_numbers": result.get("reading_the_numbers"),
        "full_result": manifest,
        "how_to_read": (
            "The complete brief is saved. Read any part with "
            "read_run_section(name='geo_demand', section='brief') — that is "
            "where the questions and the answer-first instructions are — "
            "paging with page= when `more` is true. Do not re-run the graph to "
            "see it; it costs money and the data is already here."
        ),
    }


def _previous_result() -> dict | None:
    """The GEO brief already recorded on this run, if any."""
    from .. import runs as runs_store

    run_id = rec.active_run_id()
    if not run_id:
        return None
    run = runs_store.get_run(run_id)
    for stage in (run or {}).get("stages", []):
        if stage.get("id") == "ai_citability":
            artifact = stage.get("artifact") or {}
            inner = artifact.get("artifact") if isinstance(artifact.get("artifact"), dict) else artifact
            if inner.get("brief"):
                return inner
    return None


def run_geo_demand(
    topics: list[str],
    location_code: int | None = None,
    language_code: str | None = None,
    max_question_terms: int = MAX_QUESTION_TERMS,
    max_mention_terms: int = MAX_MENTION_TERMS,
    wide_competitive_scan: bool = True,
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

    # Re-entry guard. Observed 2026-09-01: after the graph completed for three
    # topics the agent called it again for a subset of two, which re-billed the
    # per-keyword paid call for topics already measured. Nothing about the flow
    # invites a second pass, so refuse it and hand back what exists — but only
    # when the new request adds nothing, so a genuinely new topic still runs.
    previous = _previous_result()
    if previous:
        already = {str(t).lower() for t in previous.get("topics_examined") or []}
        fresh = [t for t in clean if t.lower() not in already]
        if not fresh:
            rec.log_activity(
                "step",
                detail="GEO already ran for these topics — returning the existing "
                       "brief instead of paying for it twice",
            )
            return {
                **_handoff(previous),
                "reused": True,
                "note": (
                    "These topics were already measured in this run, so the "
                    "existing brief is returned rather than re-billing the paid "
                    "per-keyword call. Pass new topics to research something else."
                ),
            }
        clean = fresh

    steps: list[str] = []

    rec.log_activity("step", detail=f"node: search demand for {len(clean)} topics (1 call)")
    demand = _demand_rows(clean, loc, lang)
    rec.record_tool("keyword_overview", {"location_code": loc, "language_code": lang},
                    demand, True)
    steps.append("demand")

    # Shortlist BEFORE the expensive call. search_mentions is ~$0.10 per
    # keyword, so running it on every candidate pays for topics that the cheap
    # volume check already showed are dead. Order by measured volume and keep
    # the top few that have any.
    with_volume = sorted(
        (r for r in demand if (r.get("volume") or 0) > 0),
        key=lambda r: r.get("volume") or 0, reverse=True,
    )
    shortlist = [r["keyword"] for r in with_volume[:max_mention_terms]]
    no_volume = [r["keyword"] for r in demand if (r.get("volume") or 0) <= 0]
    # Nothing had volume: fall back to the original list rather than give up —
    # a niche topic can still be worth writing if AI engines answer it.
    if not shortlist:
        shortlist = clean[:max_mention_terms]
        no_volume = []
    dropped_before_paid_call = [
        r["keyword"] for r in with_volume[max_mention_terms:]
    ] + no_volume
    rec.log_activity(
        "step",
        detail=f"node: shortlist {len(shortlist)} of {len(clean)} for the paid "
               f"AI-citability call (skipping {len(dropped_before_paid_call)})",
    )
    steps.append("shortlist")

    rec.log_activity(
        "step",
        detail=f"node: AI citability — {len(shortlist) * (2 if wide_competitive_scan else 1)} "
               f"paid calls ({'question + answer scope' if wide_competitive_scan else 'question scope'})",
    )
    citability = _citability(shortlist, loc, lang, wide=wide_competitive_scan)
    steps.append("citability")

    rec.log_activity("step", detail="node: grade the sites AI engines cite")
    competition = _displaceability(citability)
    steps.append("displaceability")

    rec.log_activity("step", detail="node: rank topics on measured demand")
    measured = [r for r in demand if r["keyword"] in set(shortlist)]
    ranked = _rank(measured, citability, competition)
    steps.append("ranked")

    # Harvest questions only where the evidence justifies a SERP call.
    with_demand = [r for r in ranked if r["ai_questions_found"] or r["search_volume"]]
    winners = with_demand[:max_question_terms] or ranked[:1]

    # Two different reasons a topic gets no questions, reported separately.
    # Collapsing them labelled a topic with 5,400/mo and 42 AI questions as
    # "no demand" simply because it ranked below the cap.
    no_demand = [r["topic"] for r in ranked if r not in with_demand]
    capped = [
        {"topic": r["topic"], "search_volume": r["search_volume"],
         "ai_questions_found": r["ai_questions_found"]}
        for r in with_demand[max_question_terms:]
    ]

    rec.log_activity(
        "step",
        detail=f"node: People-also-ask for the top {len(winners)} "
               f"({len(no_demand)} had no demand, {len(capped)} had demand "
               f"but fell below the cap of {max_question_terms})",
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
                # Near-always 1.0 / 0.0: Google AI Overview answers almost
                # everything, so these say little. Judge the opportunity on
                # can_you_displace_them instead.
                "answered_share": row["answered_share"],
                "open_share": row["open_share"],
                "weakest_cited_authority": row["weakest_cited_authority"],
                "strongest_cited_authority": row["strongest_cited_authority"],
            },
            "currently_cited": row["cited_sources"],
            "can_you_displace_them": row["displaceability"],
            "niche_sites_already_cited": [
                {"domain": d["domain"], "authority_rank": d["authority_rank"]}
                for d in row["niche_sites_cited"]
            ],
            "questions_people_ask": [q.get("question") for q in paa][:10],
            "questions_ai_answers": [q.get("question") for q in ai_questions][:10],
            # Ready-to-write sections, so the output is a content plan rather
            # than a data dump the reader has to interpret.
            "content_plan": _content_plan(row, paa, ai_questions),
            "how_to_use_this": (
                "Each content_plan entry is one page section: the question is "
                "the heading, and the first two sentences under it must BE the "
                "answer. That is what a generative engine can lift and cite. "
                "Depth, opinion and story go after it, not before."
            ),
        })

    result = {
        "success": True,
        "market": market["label"],
        "topics_examined": clean,
        "ranked": ranked,
        "brief": brief,
        "skipped_no_demand": no_demand,
        "had_demand_but_capped": capped,
        "not_sent_to_paid_call": dropped_before_paid_call,
        "cost_note": (
            f"1 keyword_overview call for all {len(clean)} candidates, "
            f"{len(shortlist) * (2 if wide_competitive_scan else 1)} search_mentions "
            f"calls (the expensive one, ~$0.10 each; two scopes per topic when "
            f"the wide competitive scan is on) on the shortlist, "
            f"1 bulk domain-rank call, and "
            f"{len(questions)} People-also-ask calls."
        ),
        "steps": steps,
        "method": (
            "Search volume and AI presence are measured from DataForSEO; the "
            "ranking is arithmetic over those measurements and publishes its "
            "inputs. The expensive per-keyword search_mentions call ran only on "
            "the shortlist that the cheap volume check kept, and "
            "People-also-ask only on the final winners."
        ),
        "reading_the_numbers": (
            "ai_search_volume is a SUM across every question matched for the "
            "topic, and for Google AI Overviews DataForSEO derives it from "
            "Google search volume — so it sizes the question cluster and is NOT "
            "a separate AI demand channel. Do not compare it against "
            "search_volume for a single head term. answered_share/open_share "
            "are near-constant because AI Overview answers nearly everything; "
            "judge the opportunity on can_you_displace_them."
        ),
        "platforms_measured": sorted({
            q.get("platform", "") for geo in citability.values()
            for q in geo.get("questions", []) if q.get("platform")
        }),
    }
    # Full artifact to the stage (UI + WebMCP read this), summary to the model.
    rec.record_deliverable("ai_citability", "GEO demand brief", result)
    rec.log_activity("step", detail="graph complete")
    return _handoff(result)
