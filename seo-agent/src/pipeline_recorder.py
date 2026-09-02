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
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import runs

_active_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_run_id", default=None
)

# Live activity feed per run (LLM rounds, tool starts/ends) — in-memory only,
# drained by the orchestrator stream and the /activity REST endpoint so the
# UI is never blind between stage completions.
_ACTIVITY_LOCK = threading.Lock()
_ACTIVITY: dict[str, list[dict]] = {}
_ACTIVITY_MAX = 500


def log_activity(
    kind: str,
    tool: str | None = None,
    success: bool | None = None,
    detail: str = "",
) -> None:
    """Append a live activity event to the active run (no-op outside a run)."""
    run_id = _active_run_id.get()
    if not run_id:
        return
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "tool": tool,
        "success": success,
        "detail": (detail or "")[:300],
    }
    with _ACTIVITY_LOCK:
        events = _ACTIVITY.setdefault(run_id, [])
        events.append(event)
        if len(events) > _ACTIVITY_MAX:
            del events[: len(events) - _ACTIVITY_MAX]


def new_activity(run_id: str, cursor: int) -> tuple[list[dict], int]:
    """Activity events recorded after `cursor`, plus the next cursor."""
    with _ACTIVITY_LOCK:
        events = list(_ACTIVITY.get(run_id, [])[cursor:])
    return events, cursor + len(events)

STAGE_LABELS = {
    "intake": "Intake",
    "seeds": "Seeds",
    "keywords": "Keyword discovery",
    "clusters": "Clusters",
    "pillars": "Content pillars",
    "mix": "Content mix",
    "audit": "Technical audit",
    "competitors": "Competitor map",
    "onpage": "On-page recommendations",
    "ai_citability": "AI citability",
}

# Google Ads location codes used by DataForSEO -> human market labels
MARKET_LABELS = {
    2840: "US", 2826: "UK", 2100: "BG", 2056: "BE", 2250: "FR",
    2276: "DE", 2528: "NL", 2724: "IE", 2036: "AU", 2124: "CA",
    2704: "ES", 2380: "IT", 2616: "PL", 2642: "RO", 2300: "GR",
}

KEYWORD_TOOLS = {"keyword_suggestions", "related_keywords", "keywords_for_site", "keyword_overview", "pull_universe"}

AUDIT_TOOLS = {
    "technical_seo_audit", "audit_crawlability", "audit_meta_tags",
    "audit_structured_data", "audit_performance", "audit_mobile",
    "audit_i18n", "audit_content",
}

COMPETITOR_TOOLS = {
    "competitors_domain", "domain_intersection",
    "serp_organic", "serp_ai_mode",
}


def _trim(value, max_items: int = 50):
    """Keep stage artifacts bounded — audit/SERP payloads can be huge."""
    if isinstance(value, list):
        return value[:max_items]
    if isinstance(value, dict):
        return {k: _trim(v, max_items) for k, v in list(value.items())[:30]}
    return value


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


def active_run_id() -> str | None:
    """The run currently open on this thread/context (None outside a run)."""
    return _active_run_id.get()


@contextmanager
def use_run(run_id: str):
    """Temporarily bind this thread/context to a run (for REST-triggered ops)."""
    token = _active_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _active_run_id.reset(token)


def end_run(run_id: str, status: str = "done") -> None:
    run = runs.get_run(run_id)
    if run:
        run["status"] = status
        run["ended"] = datetime.now(timezone.utc).isoformat()
        runs.save_run(run_id, run)
    _active_run_id.set(None)


def fail_run(run_id: str, error: str = "") -> None:
    """Close a run that crashed so it doesn't stay 'running' forever."""
    run = runs.get_run(run_id)
    if run:
        run["status"] = "error"
        run["ended"] = datetime.now(timezone.utc).isoformat()
        if error:
            run["error"] = str(error)[:500]
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


# Keyword stats live ONCE, in the keywords stage. Clusters reference keywords by
# name and anything needing volume/difficulty/CPC joins against that stage.
#
# They used to be re-embedded per cluster: on a real run that was 3,912
# characters of data already stored a few lines away, it inflated every payload
# built from clusters (the selection prompt reached 6,451 tokens), and a second
# copy is a second thing that can go stale.
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
        vols, diffs, intents, cpcs = [], [], [], []
        member_stats: dict[str, dict] = {}
        for m in members:
            s = stats.get(m.lower())
            if not s:
                continue
            row = {}
            if s.get("volume"):
                vols.append(s["volume"])
                row["volume"] = s["volume"]
            if s.get("difficulty"):
                diffs.append(s["difficulty"])
                row["difficulty"] = s["difficulty"]
            if s.get("intent"):
                intents.append(s["intent"])
                row["intent"] = s["intent"]
            if s.get("cpc"):
                cpcs.append(s["cpc"])
                row["cpc"] = s["cpc"]
            if row:
                member_stats[m] = row
        if intents:
            entry.setdefault("intent", max(set(intents), key=intents.count))
        if entry.get("avg_volume"):
            entry["total_volume"] = entry["avg_volume"] * len(members)
        elif vols:
            entry["total_volume"] = sum(vols)
        entry["avg_difficulty"] = entry.get("avg_difficulty") or (round(sum(diffs) / len(diffs)) if diffs else None)
        entry["market"] = market
        if member_stats:
            entry["keyword_stats"] = member_stats
        enriched.append(entry)
    stage = _upsert_stage(run, "clusters")
    stage["artifact"] = {"count": len(enriched), "clusters": enriched}


def _apply_selection(run: dict, result: dict) -> None:
    """Split the clusters stage into selected + discarded (with reasons)."""
    selection = result.get("selection") if isinstance(result.get("selection"), dict) else result
    selected_names = {str(n).lower() for n in selection.get("selected", []) if isinstance(n, str)}
    discard_reasons = {}
    for d in selection.get("discarded", []) or []:
        if isinstance(d, dict) and d.get("cluster_name"):
            discard_reasons[str(d["cluster_name"]).lower()] = str(d.get("reason", ""))[:300]
    # Selected clusters carry a reason too: "why this pillar" is at least as
    # useful to the reader as "why not that one", and without it the selected
    # side was the only part of the decision with no explanation attached.
    select_reasons = {}
    for entry in selection.get("selected_reasons", []) or []:
        if isinstance(entry, dict) and entry.get("cluster_name"):
            select_reasons[str(entry["cluster_name"]).lower()] = {
                "reason": str(entry.get("reason", ""))[:300],
                # A reader acting on the strategy needs to know what the cluster
                # IS and what to do with it, not only why it beat the others.
                "what_it_is": str(entry.get("what_it_is", ""))[:300],
                "how_to_use_it": str(entry.get("how_to_use_it", ""))[:300],
            }
    stage = _upsert_stage(run, "clusters")
    clusters = stage["artifact"].get("clusters", [])
    if not clusters or not selected_names:
        return  # nothing to split, or empty selection — keep as-is
    keep, dropped = [], []
    for c in clusters:
        name = str(c.get("name", "")).lower()
        head = str(c.get("head_term", "")).lower()
        if name in selected_names or head in selected_names:
            entry = dict(c)
            picked = select_reasons.get(name) or select_reasons.get(head) or {}
            entry["selection_reason"] = picked.get("reason", "")
            if picked.get("what_it_is"):
                entry["what_it_is"] = picked["what_it_is"]
            if picked.get("how_to_use_it"):
                entry["how_to_use_it"] = picked["how_to_use_it"]
            keep.append(entry)
        else:
            entry = dict(c)
            entry["discard_reason"] = discard_reasons.get(name, discard_reasons.get(head, "not selected"))
            dropped.append(entry)
    stage["artifact"]["clusters"] = keep
    stage["artifact"]["count"] = len(keep)
    stage["artifact"]["discarded"] = dropped
    stage["artifact"]["selected"] = True


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
        # `metrics` is measured from the keyword rows; opportunity is a stated
        # rule. The old seo/geo/combined scores were model estimates and are
        # gone — they are still merged when present so older runs keep rendering.
        for field in ("metrics", "opportunity", "opportunity_rule", "rationale",
                      "seo_score", "geo_score", "combined_score",
                      "seo_rationale", "geo_rationale"):
            if s.get(field) is not None:
                target[field] = s[field]


def record_tool(tool_name: str, args: dict, result, success: bool) -> None:
    """Record a finished tool call as a pipeline stage (no-op outside a run)."""
    log_activity("tool_end", tool=tool_name, success=success)
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
    elif tool_name == "select_clusters":
        _apply_selection(run, result if isinstance(result, dict) else {})
    elif tool_name == "recommend_pillars":
        stage = _upsert_stage(run, "pillars")
        stage["artifact"] = result if isinstance(result, dict) else {"pillars": result}
    elif tool_name == "plan_calendar":
        stage = _upsert_stage(run, "mix")
        stage["artifact"] = result if isinstance(result, dict) else {"calendar": result}
    elif tool_name in AUDIT_TOOLS:
        stage = _upsert_stage(run, "audit")
        checks = stage["artifact"].setdefault("checks", {})
        checks[tool_name] = _trim(result)
        stage["artifact"]["checks_count"] = len(checks)
    elif tool_name == "competitor_map":
        # The map the strategy graph builds: who was queried, what each
        # contributed, and the keywords two or more competitors share. The
        # `competitors` list is what the existing renderer shows as chips.
        stage = _upsert_stage(run, "competitors")
        m = result if isinstance(result, dict) else {}
        stage["artifact"] = {
            "competitors": list(m.get("queried") or []),
            "user_supplied": list(m.get("user") or []),
            "discovered": list(m.get("discovered") or []),
            "site_has_rankings": m.get("site_has_rankings"),
            "per_domain": m.get("per_domain") or {},
            "consensus": m.get("consensus") or [],
            "keywords_contributed": m.get("keywords_contributed", 0),
        }
    elif tool_name in COMPETITOR_TOOLS:
        stage = _upsert_stage(run, "competitors")
        sources = stage["artifact"].setdefault("sources", {})
        sources[tool_name] = _trim(result)
    elif tool_name == "ai_citability_brief":
        brief = result.get("brief") if isinstance(result, dict) else None
        if not brief:
            return
        stage = _upsert_stage(run, "ai_citability")
        stage["artifact"] = _trim(brief)
    else:
        return

    runs.save_run(run_id, run)


def record_deliverable(stage_id: str, title: str, artifact: dict) -> None:
    """Record an agent-produced deliverable as a stage (no-op outside a run).

    Unlike record_tool (which mirrors tool outputs), this stores what the
    agent itself synthesized — e.g. an on-page brief or an AI-citability brief.
    """
    run_id = _active_run_id.get()
    if not run_id:
        return
    run = runs.get_run(run_id)
    if run is None:
        return
    stage = _upsert_stage(run, stage_id)
    stage["artifact"] = _trim(artifact) if isinstance(artifact, dict) else {"content": artifact}
    stage["artifact"]["title"] = str(title)[:120]
    stage["artifact"]["source"] = "agent"
    runs.save_run(run_id, run)
