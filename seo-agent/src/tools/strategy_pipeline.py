"""Deterministic keyword-strategy pipeline (enforced process graph).

The node order and the validation gate live in CODE so the agent cannot
skip research steps or invent numbers when executing strategy work: the
LLM fills the judgment nodes (seeds, clustering, validation, selection,
pillars) while all market data flows from DataForSEO tools. Every node
logs live activity and records its stage artifact, so each step's output
is inspectable in the chat, the Run view and via WebMCP as it happens.
"""
from __future__ import annotations

import time

from .. import market as market_mod
from .. import pipeline_recorder as rec
from .run_sections import stage_manifest
from .cluster_keywords import cluster_keywords
from .extract_seeds import extract_seeds
from .pull_universe import pull_universe
from .recommend_pillars import recommend_pillars
from .score_clusters import score_clusters
from .select_clusters import select_clusters
from .strategy_brief import write_brief
from . import site_fetch
from .. import errors
from .. import runs as runs_store
from .serp_verify import apply_merges, verify_clusters
from .validate_clusters import validate_clusters


def _norm_clusters(raw) -> list[dict]:
    """Normalize cluster_keywords LLM output to [{name, keywords: [str], ...}]."""
    if isinstance(raw, dict):
        raw = raw.get("clusters", raw)
        if isinstance(raw, dict):
            return [
                {
                    "cluster_id": i,
                    "name": str(name),
                    "keywords": [k for k in (kws if isinstance(kws, list) else []) if isinstance(k, str)],
                }
                for i, (name, kws) in enumerate(raw.items(), 1)
            ]
    if isinstance(raw, list):
        out = []
        for i, c in enumerate(raw, 1):
            if not isinstance(c, dict):
                continue
            name = c.get("cluster_name") or c.get("name") or c.get("theme") or f"Cluster {i}"
            kws = c.get("keywords") or []
            if kws and isinstance(kws[0], dict):
                kws = [k.get("keyword") for k in kws if isinstance(k, dict) and k.get("keyword")]
            entry = dict(c)
            entry.update({
                "cluster_id": c.get("cluster_id", i),
                "name": str(name),
                "keywords": [k for k in kws if isinstance(k, str)],
            })
            out.append(entry)
        return out
    return []


def _head_term(cluster: dict) -> str:
    head = cluster.get("head_term")
    if isinstance(head, str) and head.strip():
        return head.strip()
    return cluster.get("name", "").strip()


def _cluster_with_retry(
    keywords: list[dict],
    location_code: int | None,
    language_code: str | None,
    max_clusters: int = 10,
) -> dict:
    """cluster_keywords with one bounded retry.

    Clustering is the largest LLM call in the graph; slow/queued endpoints
    can hold it past the timeout. Retrying here (after a short pause) is far
    cheaper than letting the outer agent re-run the whole graph, which would
    re-bill DataForSEO for seeds + universe.
    """
    clustered = cluster_keywords(
        keywords, max_clusters=max_clusters,
        location_code=location_code, language_code=language_code,
    )
    if clustered.get("success"):
        return clustered
    rec.log_activity("step", detail="cluster node: LLM failed, retrying once")
    time.sleep(10)
    return cluster_keywords(
        keywords, max_clusters=max_clusters,
        location_code=location_code, language_code=language_code,
    )


def _handoff(result: dict) -> dict:
    """Persist the full result, hand back a manifest plus the headline numbers.

    NOT a summary. An earlier version picked "the important fields", which put
    one person's guess about what matters between the agent and its own work,
    and then told it not to ask for more — so anything dropped was simply gone
    at the step where judgement matters most.

    Instead the complete result goes to disk and the agent is told what exists
    and how to read it. It decides what it needs; long sections come back in
    pages rather than truncated.
    """
    manifest = stage_manifest(rec.active_run_id() or "")
    return {
        # Numbers small enough to carry inline, so the common case needs no
        # follow-up read.
        "success": result.get("success"),
        "market": result.get("market"),
        "keyword_count": result.get("keyword_count"),
        "cluster_count": result.get("cluster_count"),
        "steps": result.get("steps"),
        "validation_verdict": result.get("validation_verdict"),
        "validation_warning": result.get("validation_warning"),
        "relevance_gate_ran": result.get("relevance_gate_ran"),
        "selection_warning": result.get("selection_warning"),
        "selected_clusters": result.get("selected_clusters"),
        # Everything else, addressable.
        "recorded_stages": manifest.get("stages"),
        "how_to_read": (
            "The complete result is saved. Read any part with "
            "read_run_section(name='keyword_strategy', section='<section>'), "
            "paging with page= when `more` is true. Sections and their sizes "
            "are listed in full_result.sections — read what you actually need "
            "rather than assuming what is there."
        ),
    }


def _domain_only(url: str) -> str:
    u = (url or "").strip()
    if not u or " " in u:
        return ""
    u = u.split("://", 1)[-1].split("/", 1)[0]
    return u.removeprefix("www.")


def run_keyword_strategy(*args, **kwargs) -> dict:
    """The graph, with any raised node turned into a stopped step. The agent
    is told which step and that a retry is safe; the exception itself goes
    to the log, not to a bubble."""
    _current_step["name"] = "starting"
    try:
        return _run_keyword_strategy(*args, **kwargs)
    except Exception as e:
        step = _current_step.get("name") or "an unknown step"
        print(f"[strategy graph] stopped at {step}: {errors.detail(e)}")
        try:
            rec.log_activity("step", detail=f"stopped at {step}")
        except Exception:
            pass
        return {
            "success": False,
            "stopped_at": step,
            "error": f"The strategy pipeline stopped while {step}. Nothing was invented; the stages it finished are on the artefact. Retrying is safe.",
            "retry_is_safe": errors.is_recoverable(e),
        }


_current_step: dict[str, str] = {"name": ""}


def _step(name: str) -> None:
    _current_step["name"] = name


def _run_keyword_strategy(
    business_description: str,
    location_code: int | None = None,
    language_code: str | None = None,
    site_description: str = "",
    competitor_urls: list[str] | None = None,
    max_select: int = 4,
    own_urls: list[str] | None = None,
) -> dict:
    """Run the enforced strategy graph end-to-end inside the active run.

    Nodes: seeds -> keyword universe (DataForSEO) -> over-cluster (10) ->
    validate gate (<=2 attempts) -> score -> select top N
    brief on selected head terms -> pillars from the selection only.
    """
    if not rec.active_run_id():
        return {"success": False, "error": "run_keyword_strategy must run inside a pipeline run"}
    if not (business_description or "").strip():
        return {"success": False, "error": "business_description is required"}

    # Market gate. There are deliberately no location/language defaults: a
    # guessed market is what produced Bulgarian theatre keywords for a poetry
    # site. The user must confirm country + language first.
    try:
        market = market_mod.require_market(location_code, language_code)
    except market_mod.MarketNotConfirmed as exc:
        return {"success": False, "error": str(exc), "needs": "confirm_market"}
    location_code = market["location_code"]
    language_code = market["language_code"]
    rec.log_activity("step", detail=f"market: {market['label']}")

    steps: list[str] = []

    # Every URL the user typed, read from the message itself. The model that
    # fills the tool call drops some — a run that got three competitors was
    # given more — so the prompt is the source of truth and the tool call is
    # merged into it, not the other way round.
    run_now = runs_store.get_run(rec.active_run_id()) if rec.active_run_id() else None
    prompt_text = (run_now or {}).get("prompt") or ""
    found = site_fetch.classify_urls(prompt_text, site_description)
    site_url = site_description if site_fetch.domain_of(site_description) else ""
    if not site_url and found["own"]:
        site_url = found["own"][0]
    own_pages = []
    seen_own = set()
    for u in list(own_urls or []) + ([site_url] if site_url else []) + found["own"]:
        d = site_fetch.domain_of(u)
        if u and d and u not in seen_own:
            seen_own.add(u)
            own_pages.append(u)
    own_domains = {site_fetch.domain_of(u) for u in own_pages}
    competitors = []
    seen_c = set()
    for u in list(competitor_urls or []) + found["competitors"]:
        d = site_fetch.domain_of(u)
        if d and d not in seen_c and d not in own_domains:
            seen_c.add(d)
            competitors.append(u)
    competitors = competitors[:10]
    if len(found["own"]) + len(found["competitors"]) > 0:
        rec.log_activity("step", detail=(
            f"links: {len(own_pages)} of yours, {len(competitors)} competitors "
            f"({len(found['competitors'])} read from your message)"))

    # Read the user's own pages so the seeds come from what they say.
    site_blocks = []
    for u in own_pages[:4]:
        rec.log_activity("step", detail=f"reading your page: {site_fetch.domain_of(u)}")
        page = site_fetch.fetch_page(u)
        site_blocks.append(site_fetch.page_summary_for_prompt(page, site_fetch.domain_of(u) or u))
        if page.get("ok"):
            rec.record_tool("read_page", {"url": u},
                            {"url": page.get("url"), "title": page.get("title"),
                             "headings": page.get("headings", [])[:25]}, True)
    site_content = "\n\n".join(site_blocks)
    if site_url and not site_description:
        site_description = site_url

    _step("building seeds")
    rec.log_activity("step", detail="node: extract seeds")
    seeds = extract_seeds(business_description, site_description, competitors,
                          language_code=language_code, site_content=site_content)
    rec.record_tool("extract_seeds", {"business_description": business_description}, seeds, True)
    steps.append("seeds")
    run_id_now = rec.active_run_id()
    if run_id_now and isinstance(seeds, dict) and seeds.get("business_name"):
        domain = _domain_only(site_description)
        rec.name_run(
            run_id_now, str(seeds["business_name"]),
            " · ".join(x for x in (domain, "Content strategy", market.get("label", "")) if x),
        )

    _step("pulling keyword data")
    rec.log_activity("step", detail="node: keyword universe via DataForSEO")
    universe = pull_universe(
        seeds, location_code=location_code, language_code=language_code,
        competitor_urls=competitors, site_url=site_url or site_description,
        business_description=business_description,
    )
    keywords = universe.get("keywords") or []
    rec.record_tool(
        "pull_universe",
        {"location_code": location_code, "language_code": language_code},
        universe, True,
    )
    comp = universe.get("competitors") or {}
    if not comp.get("queried"):
        rec.log_activity("step", detail="competitors: none to check — add competitor URLs to the brief for a stronger universe")
    if comp.get("queried"):
        rec.record_tool("competitor_map", {"competitor_urls": competitors}, comp, True)
        rec.log_activity(
            "step",
            detail=(f"competitors: {len(comp['queried'])} queried "
                    f"({len(comp.get('user') or [])} supplied, {len(comp.get('discovered') or [])} discovered), "
                    f"{comp.get('keywords_contributed', 0)} keywords, "
                    f"{len(comp.get('consensus') or [])} ranked by two or more"
                    + (f"; relevance gate kept {comp['relevance']['kept']}, dropped {comp['relevance']['dropped']}"
                       if (comp.get('relevance') or {}).get('ran') else "")),
        )
    if not keywords:
        # pull_universe keeps the seeds themselves as a floor, so reaching this
        # means seed extraction produced nothing — not a normal thin-market case.
        return {
            "success": False,
            "error": "keyword universe is empty (seed extraction returned no seeds; DataForSEO budget may be exhausted)",
            "steps": steps,
        }
    if len(keywords) < 15:
        rec.log_activity(
            "step",
            detail=f"note: thin market — only {len(keywords)} keywords, "
            "strategy leans on the seeds/competitor fallback rather than volume data",
        )
    steps.append("keywords")

    _step("grouping keywords into themes")
    rec.log_activity("step", detail=f"node: cluster {len(keywords)} keywords (over-generate 10)")
    clustered = _cluster_with_retry(keywords, location_code, language_code)
    clusters = _norm_clusters(clustered.get("clusters"))
    if not clustered.get("success") or not clusters:
        return {"success": False, "error": clustered.get("error") or "clustering failed", "steps": steps}
    rec.record_tool(
        "cluster_keywords",
        {"keywords": keywords, "location_code": location_code, "language_code": language_code},
        {"clusters": clusters}, True,
    )
    steps.append("clusters")

    # SERP verification. Thematic clustering asks whether keywords sound alike;
    # this asks whether Google returns the same results for them, which is the
    # question that decides how many pages to write.
    #
    # Measured on a real run: "ai product manager course" and "ai product
    # manager certification" share 89% of their top-10 results — the model had
    # them as separate clusters, and four course clusters collapsed into one.
    # In the other direction "knowledge graphs for AI products" and "knowledge
    # graph RAG" share NOTHING, so merging them on the words alone would have
    # produced a page ranking for neither.
    #
    # Only pairs whose head terms already share vocabulary are checked, so
    # unrelated clusters cost nothing, and an unverified pair stays separate —
    # splitting effort is recoverable, a wrongly merged page is not.
    _step("verifying themes against live results")
    rec.log_activity("step", detail="node: verify clusters against live SERPs")
    verification = verify_clusters(clusters, location_code, language_code)
    if verification.get("merges"):
        before = len(clusters)
        clusters = apply_merges(clusters, verification)
        rec.log_activity(
            "step",
            detail=f"SERP evidence merged {before} clusters into {len(clusters)} "
                   f"({verification['checked']} SERP calls)",
        )
        rec.record_tool(
            "cluster_keywords",
            {"keywords": keywords, "location_code": location_code,
             "language_code": language_code},
            {"clusters": clusters}, True,
        )
    else:
        rec.log_activity(
            "step",
            detail=f"SERP check: no merges ({verification['checked']} calls, "
                   f"{verification.get('pairs_considered', 0)} pairs considered)",
        )
    steps.append("serp_verified")

    # Validation gate: approve, or re-cluster once on needs_revision (bounded).
    #
    # The re-cluster only happens if another validation will follow. Previously
    # the loop re-clustered after the LAST attempt too, so the clusters that
    # actually reached scoring, selection and pillars were the output of a
    # third clustering that nobody ever validated — the gate exists to stop
    # exactly that. Observed 2026-09-01: two needs_revision verdicts, then a
    # third unchecked clustering carried the whole strategy, at 25s of extra
    # cost for negative value.
    # ONE pass by default. Measured 2026-09-01:
    #   - the live run validated twice, got needs_revision both times, and the
    #     re-cluster between them changed nothing but cost ~130s;
    #   - an A/B on the same clusters showed max and flash produce the SAME
    #     critique (both scored the catch-all cluster 32, rec=split), so the
    #     critique is the valuable part, not the retry;
    #   - the verdict is knife-edge: "rejected" vs "needs_revision" turned on
    #     one borderline cluster scoring 57 rather than 60, and only the
    #     latter triggers the expensive retry.
    # The critique now travels to the user via validation_warning instead of
    # being spent on a re-cluster that does not act on it. Raise this if a
    # future change makes the retry actually use the issues it was given.
    MAX_ATTEMPTS = 1
    verdict = "rejected"
    validation: dict = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _step("reviewing the themes")
        rec.log_activity("step", detail=f"node: validate clusters (attempt {attempt})")
        validation = validate_clusters(
            {c["name"]: c["keywords"] for c in clusters},
            seeds=seeds, domain_description=business_description,
        )
        verdict = str(validation.get("verdict") or "rejected")
        if verdict in ("approved", "rejected"):
            break
        if attempt == MAX_ATTEMPTS:
            # Out of attempts: keep the set that was actually just validated,
            # and let the verdict travel with the result so the answer can say
            # the clusters were never approved.
            rec.log_activity(
                "step",
                detail="gate: still needs_revision after the final attempt — "
                       "continuing with the validated clusters and flagging it",
            )
            break
        rec.log_activity("step", detail="gate: needs_revision -> re-clustering")
        reclustered = _cluster_with_retry(
            keywords, location_code, language_code,
            max_clusters=max(6, len(clusters) - 2),
        )
        clusters = _norm_clusters(reclustered.get("clusters")) or clusters
        rec.record_tool(
            "cluster_keywords",
            {"keywords": keywords, "location_code": location_code, "language_code": language_code},
            {"clusters": clusters}, True,
        )

    _step("measuring the themes")
    rec.log_activity("step", detail="node: compute cluster metrics")
    # Deterministic now — pass the keyword universe so each cluster's volume,
    # difficulty, CPC and intent mix are measured from the real rows.
    scored = score_clusters({"clusters": clusters}, keywords=keywords) or {}
    rec.record_tool("score_clusters", {}, scored, True)

    _step("choosing the themes")

    rec.log_activity("step", detail=f"node: select top {max_select} clusters")
    selection_res = select_clusters(
        scored or {"clusters": clusters},
        max_select=max_select,
        business_description=business_description,
    )
    # Selection is the RELEVANCE GATE — the only node that asks "does this
    # cluster serve THIS business". One transient LLM failure should not
    # silently skip it, so retry once before falling back.
    if not selection_res.get("success") or not selection_res.get("selection", {}).get("selected"):
        rec.log_activity(
            "step",
            detail=f"relevance gate failed ({str(selection_res.get('error'))[:80]}) — retrying once",
        )
        selection_res = select_clusters(
            scored or {"clusters": clusters},
            max_select=max_select,
            business_description=business_description,
        )

    selection_error = ""
    selection_failed = (
        not selection_res.get("success")
        or not selection_res.get("selection", {}).get("selected")
    )
    if selection_failed:
        # The old fallback took names[:max_select] — the first N in whatever
        # order clustering happened to emit — and labelled the rest "not
        # selected (deterministic fallback)". That reads like a decision and is
        # not one. Observed 2026-09-01: it kept three near-duplicate
        # course-buying clusters and discarded "Building AI Products",
        # "Agentic AI Development" and "AI Product Evaluation" — the subject
        # the business is actually about — with no relevance judgement made at
        # any point, and nothing in the output saying so.
        #
        # Rank by MEASURED opportunity instead of emission order, and say
        # plainly on every entry that relevance was never assessed.
        selection_error = str(selection_res.get("error") or "no usable selection returned")[:200]
        ranked = sorted(
            clusters,
            key=lambda c: (c.get("metrics") or {}).get("total_volume", 0),
            reverse=True,
        )
        keep = [c["name"] for c in ranked[:max_select]]
        rec.log_activity(
            "step",
            detail="relevance gate UNAVAILABLE — ranked by search volume only; "
                   "the selection is not a relevance judgement",
        )
        selection_res = {
            "success": True,
            "selection": {
                "selected": keep,
                "selected_reasons": [
                    {
                        "cluster_name": n,
                        "reason": (
                            "Kept by SEARCH VOLUME only — the relevance step "
                            "failed, so no one checked whether this serves your "
                            "business. Review before building on it."
                        ),
                    }
                    for n in keep
                ],
                "discarded": [
                    {
                        "cluster_name": c["name"],
                        "reason": (
                            "Dropped by search volume only — the relevance step "
                            "failed, so this was NOT judged off-topic. It may "
                            "well be the right cluster; promote it if so."
                        ),
                    }
                    for c in ranked[max_select:]
                ],
            },
        }
    rec.record_tool("select_clusters", {}, selection_res, True)
    steps.append("selection")

    selected_names = {str(n).lower() for n in selection_res["selection"]["selected"]}
    selected = [c for c in clusters if c["name"].lower() in selected_names] or clusters[:max_select]
    head_terms = [_head_term(c) for c in selected if _head_term(c)][:6]

    # AI-citability is NOT part of the content strategy. It sat here as a
    # paid step after selection whose output the pillars never read, and it
    # made the strategy report look like it was about AI answers when it is
    # about search. It lives in the GEO flow, where it is the whole point.
    brief: dict = {}

    _step("writing the content pillars")
    rec.log_activity("step", detail="node: pillars from selected clusters only")
    scored_list = scored.get("scored_clusters") or scored.get("clusters") or []
    if isinstance(scored_list, list):
        sel_scored = [
            s for s in scored_list
            if isinstance(s, dict)
            and str(s.get("cluster_name") or s.get("name") or "").lower() in selected_names
        ]
        pillars_input = {"scored_clusters": sel_scored or scored_list}
    else:
        pillars_input = scored or {"clusters": selected}
    pillars = recommend_pillars(pillars_input) or {}
    rec.record_tool("recommend_pillars", {}, pillars, True)
    steps.append("pillars")

    # The brief: the one page a reader acts on, built from the stages above.
    run_id_now = rec.active_run_id()
    if run_id_now:
        _step("writing the brief")
        rec.log_activity("step", detail="node: write the brief")
        brief_res = write_brief(run_id_now, business_description)
        if brief_res.get("ok"):
            steps.append("brief")
        else:
            rec.log_activity("step", detail=f"brief not written: {brief_res.get('error', '')[:80]}")

    rec.log_activity("step", detail="graph complete")
    return _handoff({
        "success": True,
        "market": rec.market_label(location_code, language_code),
        "keyword_count": len(keywords),
        "cluster_count": len(clusters),
        "serp_verification": {
            "checked": verification.get("checked"),
            "merges": verification.get("merges"),
            "kept_separate": verification.get("kept_separate"),
            "method": verification.get("method"),
        },
        "validation_verdict": verdict,
        "validation_issues": validation.get("global_issues", []),
        "validation_issues_detail": (validation.get("clusters") or [])[:8],
        "relevance_gate_ran": not selection_failed,
        "selection_warning": (
            ""
            if not selection_failed
            else (
                "The relevance step failed twice, so clusters were chosen by "
                "SEARCH VOLUME ALONE and nobody checked whether they serve this "
                "business. Say this plainly and offer to re-run the selection. "
                f"({selection_error})"
            )
        ),
        "validation_warning": (
            ""
            if verdict == "approved"
            else (
                f"The clustering was never approved by the validation gate "
                f"(verdict: {verdict}). The strategy below is still built on it, "
                f"so treat the pillars as a starting point and check the cluster "
                f"list before committing to it. What it flagged: "
                f"{'; '.join(str(i) for i in (validation.get('global_issues') or [])[:3]) or 'see validation_issues'}."
            )
        ),
        "selected_clusters": [c["name"] for c in selected],
        "discarded": selection_res["selection"].get("discarded", []),
        "head_terms": head_terms,
        "pillars": pillars,
        "steps": steps,
    })
