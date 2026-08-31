"""Live pipeline recording — bridges agent tool calls into the runs store.

When the orchestrator handles a chat message it opens a *run* (begin_run) and
sets it active for the duration of the specialist agent call. Every pipeline
tool the agent executes is then recorded as a stage artifact (record_tool),
so the Run view and the chat reflect the pipeline as it happens instead of
only showing seeded demo data.

Cluster stages are enriched deterministically from the DataForSEO stats that
flow through the tool arguments (volume, difficulty, intent) plus the market
(locale) captured from the research calls — no LLM judgment involved.
"""
from __future__ import annotations

import contextvars
from datetime import datetime, timezone

from . import runs

_active_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_run_id", default=None
)

STAGE_LABELS = {
    "intake": "Intake",
    "seeds": "Seeds",
    "keywords": "Keyword discovery",
    "clusters": "Clusters",
    "pillars": "Content pillars",
    "mix": "Content mix",
}

# Google Ads location codes used by DataForSEO -> human market labels
MARKET_LABELS = {
    2840: "US", 2826: "UK", 2100: "BG", 2056: "BE", 2250: "FR",
    2276: "DE", 2528: "NL", 2724: "IE", 2036: "AU", 2124: "CA",
    2704: "ES", 2380: "IT", 2616: "PL", 2642: "RO", 2300: "GR",
}

KEYWORD_TOOLS = {"keyword_suggestions", "related_keywords", "keywords_for_site", "keyword_overview"}


def market_label(location_code: int | None, language_code: str | None) -> str:
    if not location_code:
        return ""
    country = MARKET_LABELS.get(location_code, f"LOC-{location_code}")
    lang = (language_code or "").lower()
    return f"{country}-{lang.upper()}" if lang else country


def begin_run(run_id: str, title: str, project: str = "Chat pipeline") -> None:
    """Create (or reuse) the run for this chat message and make it active."""
    if runs.get_run(run_id) is None:
        runs.save_run(run_id, {
            "id": run_id,
            "project": project,
            "title": title[:80],
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "stages": [],
        })
    _active_run_id.set(run_id)


def end_run(run_id: str) -> None:
    run = runs.get_run(run_id)
    if run:
        run["status"] = "done"
        runs.save_run(run_id, run)
    _active_run_id.set(None)


def stage_ids(run_id: str) -> set[str]:
    run = runs.get_run(run_id)
    return {s["id"] for s in run.get("stages", [])} if run else set()


def new_stages(run_id: str, before: set[str]) -> list[dict]:
    """Stages added to the run since `before` was captured, in pipeline order."""
    run = runs.get_run(run_id)
    if not run:
        return []
    return [{"stage_id": s["id"], "label": s["label"]} for s in run.get("stages", []) if s["id"] not in before]


def _upsert_stage(run: dict, stage_id: str) -> dict:
    for stage in run["stages"]:
        if stage["id"] == stage_id:
            return stage
    stage = {"id": stage_id, "label": STAGE_LABELS.get(stage_id, stage_id), "status": "done", "artifact": {}}
    run["stages"].append(stage)
    return stage


def _capture_locale(run: dict, args: dict) -> None:
    loc = args.get("location_code")
    lang = args.get("language_code")
    if not loc:
        return
    intake = _upsert_stage(run, "intake")
    intake["artifact"]["locale"] = {"location_code": loc, "language_code": lang}
    intake["artifact"]["market"] = market_label(loc, lang)


def _record_keywords(run: dict, result) -> None:
    keywords = result if isinstance(result, list) else result.get("keywords") or result.get("results") or []
    if not isinstance(keywords, list) or not keywords:
        return
    stage = _upsert_stage(run, "keywords")
    existing = {k.get("keyword", "").lower(): k for k in stage["artifact"].get("keywords", [])}
    for kw in keywords:
        if not isinstance(kw, dict) or not kw.get("keyword"):
            continue
        existing.setdefault(kw["keyword"].lower(), kw)
    merged = list(existing.values())
    stage["artifact"] = {"count": len(merged), "keywords": merged}


def _kw_stats(args: dict) -> dict[str, dict]:
    stats = {}
    for kw in args.get("keywords", []) or []:
        if isinstance(kw, dict) and kw.get("keyword"):
            stats[kw["keyword"].lower()] = kw
    return stats


def _record_clusters(run: dict, args: dict, result: dict) -> None:
    clusters = result.get("clusters")
    if isinstance(clusters, dict):
        clusters = clusters.get("clusters", [])
    if not isinstance(clusters, list):
        return
    stats = _kw_stats(args)
    market = (run["stages"] and _market_of(run)) or ""
    enriched = []
    for i, c in enumerate(clusters, 1):
        if not isinstance(c, dict):
            continue
        entry = dict(c)
        entry.setdefault(
            "name",
            entry.get("cluster_name") or entry.get("head_term") or f"Cluster {entry.get('cluster_id', i)}",
        )
        members = [k for k in entry.get("keywords", []) if isinstance(k, str)]
        vols, diffs, intents = [], [], []
        for m in members:
            s = stats.get(m.lower())
            if not s:
                continue
            if s.get("volume"):
                vols.append(s["volume"])
            if s.get("difficulty"):
                diffs.append(s["difficulty"])
            if s.get("intent"):
                intents.append(s["intent"])
        if intents:
            entry.setdefault("intent", max(set(intents), key=intents.count))
        if entry.get("avg_volume"):
            entry["total_volume"] = entry["avg_volume"] * len(members)
        elif vols:
            entry["total_volume"] = sum(vols)
        entry["avg_difficulty"] = entry.get("avg_difficulty") or (round(sum(diffs) / len(diffs)) if diffs else None)
        entry["market"] = market
        enriched.append(entry)
    stage = _upsert_stage(run, "clusters")
    stage["artifact"] = {"count": len(enriched), "clusters": enriched}


def _market_of(run: dict) -> str:
    for stage in run["stages"]:
        if stage["id"] == "intake":
            return stage["artifact"].get("market", "")
    return ""


def _record_scores(run: dict, result: dict) -> None:
    scored = result.get("scored_clusters") or result.get("clusters") or []
    if not isinstance(scored, list):
        return
    stage = _upsert_stage(run, "clusters")
    clusters = stage["artifact"].get("clusters", [])
    if not clusters:
        return  # scoring without a recorded clustering step — nothing to merge into
    by_name = {c.get("name", "").lower(): c for c in clusters}
    for s in scored:
        if not isinstance(s, dict):
            continue
        name = (s.get("cluster_name") or s.get("name") or "").lower()
        target = by_name.get(name)
        if target is None:
            continue
        for field in ("seo_score", "geo_score", "combined_score", "seo_rationale", "geo_rationale", "opportunity", "rationale"):
            if s.get(field) is not None:
                target[field] = s[field]


def record_tool(tool_name: str, args: dict, result, success: bool) -> None:
    """Record a finished tool call as a pipeline stage (no-op outside a run)."""
    run_id = _active_run_id.get()
    if not run_id or not success or result is None:
        return
    run = runs.get_run(run_id)
    if run is None:
        return

    _capture_locale(run, args or {})

    if tool_name == "extract_seeds":
        stage = _upsert_stage(run, "seeds")
        stage["artifact"] = result if isinstance(result, dict) else {"seeds": result}
    elif tool_name in KEYWORD_TOOLS:
        _record_keywords(run, result)
    elif tool_name == "cluster_keywords":
        _record_clusters(run, args or {}, result if isinstance(result, dict) else {})
    elif tool_name == "score_clusters":
        _record_scores(run, result if isinstance(result, dict) else {})
    elif tool_name == "recommend_pillars":
        stage = _upsert_stage(run, "pillars")
        stage["artifact"] = result if isinstance(result, dict) else {"pillars": result}
    elif tool_name == "plan_calendar":
        stage = _upsert_stage(run, "mix")
        stage["artifact"] = result if isinstance(result, dict) else {"calendar": result}
    else:
        return

    runs.save_run(run_id, run)
