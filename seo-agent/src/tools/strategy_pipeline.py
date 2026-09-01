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
from .ai_citability import ai_citability_brief
from .cluster_keywords import cluster_keywords
from .extract_seeds import extract_seeds
from .pull_universe import pull_universe
from .recommend_pillars import recommend_pillars
from .score_clusters import score_clusters
from .select_clusters import select_clusters
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


def run_keyword_strategy(
    business_description: str,
    location_code: int | None = None,
    language_code: str | None = None,
    site_description: str = "",
    competitor_urls: list[str] | None = None,
    max_select: int = 4,
) -> dict:
    """Run the enforced strategy graph end-to-end inside the active run.

    Nodes: seeds -> keyword universe (DataForSEO) -> over-cluster (10) ->
    validate gate (<=2 attempts) -> score -> select top N -> AI-citability
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

    competitors = competitor_urls or []
    steps: list[str] = []

    rec.log_activity("step", detail="node: extract seeds")
    seeds = extract_seeds(business_description, site_description, competitors, language_code=language_code)
    rec.record_tool("extract_seeds", {"business_description": business_description}, seeds, True)
    steps.append("seeds")

    rec.log_activity("step", detail="node: keyword universe via DataForSEO")
    universe = pull_universe(
        seeds, location_code=location_code, language_code=language_code,
        competitor_urls=competitors,
    )
    keywords = universe.get("keywords") or []
    rec.record_tool(
        "pull_universe",
        {"location_code": location_code, "language_code": language_code},
        universe, True,
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

    rec.log_activity("step", detail="node: compute cluster metrics")
    # Deterministic now — pass the keyword universe so each cluster's volume,
    # difficulty, CPC and intent mix are measured from the real rows.
    scored = score_clusters({"clusters": clusters}, keywords=keywords) or {}
    rec.record_tool("score_clusters", {}, scored, True)

    rec.log_activity("step", detail=f"node: select top {max_select} clusters")
    selection_res = select_clusters(
        scored or {"clusters": clusters},
        max_select=max_select,
        business_description=business_description,
    )
    if not selection_res.get("success") or not selection_res.get("selection", {}).get("selected"):
        names = [c["name"] for c in clusters]
        selection_res = {
            "success": True,
            "selection": {
                "selected": names[:max_select],
                "discarded": [
                    {"cluster_name": n, "reason": "not selected (deterministic fallback)"}
                    for n in names[max_select:]
                ],
            },
        }
    rec.record_tool("select_clusters", {}, selection_res, True)
    steps.append("selection")

    selected_names = {str(n).lower() for n in selection_res["selection"]["selected"]}
    selected = [c for c in clusters if c["name"].lower() in selected_names] or clusters[:max_select]
    head_terms = [_head_term(c) for c in selected if _head_term(c)][:6]

    brief: dict = {}
    if head_terms:
        rec.log_activity("step", detail=f"node: AI-citability brief on {len(head_terms)} head terms")
        brief = ai_citability_brief(head_terms, location_code=location_code, language_code=language_code)
        if brief.get("brief"):
            rec.record_tool("ai_citability_brief", {}, brief, True)
            steps.append("ai_citability")

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

    rec.log_activity("step", detail="graph complete")
    return {
        "success": True,
        "market": rec.market_label(location_code, language_code),
        "keyword_count": len(keywords),
        "cluster_count": len(clusters),
        "validation_verdict": verdict,
        "validation_issues": validation.get("global_issues", []),
        "validation_issues_detail": (validation.get("clusters") or [])[:8],
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
    }
