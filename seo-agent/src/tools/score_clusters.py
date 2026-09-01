"""Cluster metrics, computed — not guessed.

This node used to ask an LLM to compress volume and difficulty into invented
0-100 "SEO" and "GEO" scores plus a 0.6/0.4 composite. Measured on a real run
(2026-09-01), those numbers did not survive contact with the data:

    cluster              LLM seo_score   real total volume   real avg KD
    PM Tools                     85                  670           2.2
    PM Core Concepts             82                4,360          15.1

PM Tools was ranked the strongest SEO opportunity in the run while carrying a
sixth of the search volume of the cluster below it. The model was guessing at
arithmetic it had the inputs to compute exactly, and the composite then threw
the underlying numbers away so nobody could check it.

So: compute the real aggregates from the DataForSEO keyword rows, publish them
all, and let the reader (or their own agent) weigh them. `opportunity` remains
as a convenience, but it is a documented deterministic rule rather than a
judgment, and every input to it is published alongside so it can be recomputed
or ignored.

This also removes an LLM call worth ~80s from the graph.
"""
from __future__ import annotations

from statistics import median


# Search intents that indicate someone ready to act rather than browse.
_COMMERCIAL = {"commercial", "transactional"}


def _rows(cluster: dict, universe: dict[str, dict]) -> list[dict]:
    """The keyword rows for a cluster, with stats resolved from the universe."""
    out = []
    for kw in cluster.get("keywords") or []:
        name = kw.get("keyword") if isinstance(kw, dict) else kw
        if not name:
            continue
        stats = universe.get(str(name).lower())
        if stats:
            out.append(stats)
        elif isinstance(kw, dict):
            out.append(kw)
        else:
            out.append({"keyword": name})
    return out


def _metrics(rows: list[dict]) -> dict:
    """Aggregates over real keyword data. Every field is measured, not modelled."""
    vols = [r.get("volume") or 0 for r in rows]
    kds = [r.get("difficulty") or 0 for r in rows]
    cpcs = [r.get("cpc") or 0 for r in rows]
    intents = [str(r.get("intent") or "").lower() for r in rows]
    commercial = sum(1 for i in intents if i in _COMMERCIAL)

    return {
        "keyword_count": len(rows),
        "total_volume": sum(vols),
        "max_volume": max(vols) if vols else 0,
        "median_volume": int(median(vols)) if vols else 0,
        "avg_difficulty": round(sum(kds) / len(kds), 1) if kds else 0.0,
        "max_difficulty": max(kds) if kds else 0,
        "avg_cpc": round(sum(cpcs) / len(cpcs), 2) if cpcs else 0.0,
        "max_cpc": round(max(cpcs), 2) if cpcs else 0.0,
        "commercial_keywords": commercial,
        "commercial_share": round(commercial / len(rows), 2) if rows else 0.0,
        "top_keywords": [
            {"keyword": r.get("keyword"), "volume": r.get("volume"),
             "difficulty": r.get("difficulty"), "cpc": r.get("cpc"),
             "intent": r.get("intent")}
            for r in sorted(rows, key=lambda r: r.get("volume") or 0, reverse=True)[:5]
        ],
    }


def _opportunity(m: dict) -> dict:
    """A transparent label, with the rule that produced it stated in the output.

    Deliberately crude and explainable. It is a reading aid, not a verdict —
    relevance to the business decides selection, not this.
    """
    volume, difficulty = m["total_volume"], m["avg_difficulty"]
    if volume >= 1000 and difficulty <= 30:
        label, why = "high", "1000+ total volume at difficulty 30 or below"
    elif volume >= 300:
        label, why = "medium", "300+ total volume"
    elif volume > 0:
        label, why = "low", "under 300 total volume"
    else:
        label, why = "no volume data", "no measurable search volume for these terms"
    return {"opportunity": label, "opportunity_rule": why}


def score_clusters(clusters: dict, keywords: list[dict] | None = None) -> dict:
    """Attach measured metrics to each cluster. No LLM call.

    ``keywords`` is the run's keyword universe; when supplied, per-keyword
    stats are resolved from it so clusters holding bare keyword strings still
    get real numbers.
    """
    entries = clusters.get("clusters") or clusters.get("scored_clusters") or []
    if not isinstance(entries, list):
        return {"scored_clusters": [], "error": "clusters must be a list"}

    universe = {
        str(k.get("keyword", "")).lower(): k
        for k in (keywords or [])
        if isinstance(k, dict) and k.get("keyword")
    }

    scored = []
    for i, cluster in enumerate(entries, 1):
        if not isinstance(cluster, dict):
            continue
        metrics = _metrics(_rows(cluster, universe))
        entry = dict(cluster)
        entry.update({
            "cluster_id": cluster.get("cluster_id", i),
            "cluster_name": cluster.get("cluster_name") or cluster.get("name") or f"Cluster {i}",
            "metrics": metrics,
            **_opportunity(metrics),
        })
        scored.append(entry)

    # Ordered by measured volume so the caller sees the biggest first, but the
    # order carries no authority — every input is published for re-ranking.
    scored.sort(key=lambda c: c["metrics"]["total_volume"], reverse=True)
    return {
        "scored_clusters": scored,
        "method": (
            "Metrics are computed from the DataForSEO keyword rows for each "
            "cluster — no model estimated them. `opportunity` is a documented "
            "volume/difficulty rule (see opportunity_rule), not a judgment; "
            "rank by whichever metric matters to you."
        ),
    }
