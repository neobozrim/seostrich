"""Cluster governance — post-selection CRUD on the clusters stage artifact.

After select_clusters picks the top clusters, the user (in chat) or their
own agent (via REST/WebMCP) can still:

- list everything (selected + discarded with reasons)
- promote a discarded cluster back into the selection
- discard a selected cluster (moves it to discarded with a reason)
- propose a new cluster: a scoped DataForSEO re-seed on ONE topic,
  assembled into a cluster entry deterministically (no LLM judgment)

All ops are plain artifact mutations — other stages and clusters stay
untouched. propose_cluster is the only op that spends a DataForSEO call;
it is budget-accounted to the run being edited.
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone

from . import runs
from .tools import strategy_brief
from .pipeline_recorder import market_label, use_run


# Governance ops are read-run -> mutate -> save-whole-run. The agent dispatches
# tool calls in PARALLEL (ThreadPoolExecutor in agent.py), so several of these
# can interleave on the same run document and silently lose each other's writes.
#
# Observed 2026-09-01: seven promote/discard/propose calls fired at the same
# timestamp; a discard was reverted by a concurrent promote writing back a stale
# copy, and the agent — correctly — reported that its change had been "backfilled
# into the selection", then spent extra rounds re-applying it.
#
# One lock per run id: mutations on the same run serialise, different runs stay
# concurrent.
_run_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _run_lock(run_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _run_locks.get(run_id)
        if lock is None:
            lock = threading.Lock()
            _run_locks[run_id] = lock
        return lock


def _log_change(run: dict, op: str, cluster: str, reason: str = "",
                by: str = "agent", **extra) -> None:
    """Append one line to the run's governance history.

    Append-only and deliberately small: op, target, who, why, and the selected
    count before and after. Every governance op mutates the cluster artifact in
    place, so without this there is no record of how a strategy was shaped —
    only where it ended up. For a tool whose point is collaboration, the
    shaping IS the story.

    Full artifact snapshots per change were considered and rejected: storage
    grows fast and nobody diffs two complete states. The op plus the counts
    answers "what happened here", which is the question actually asked.

    Called inside the run lock by every mutating op, so entries cannot
    interleave or be lost the way the writes themselves once were.
    """
    stage = _clusters_stage(run)
    artifact = stage["artifact"] if stage else {}
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "by": by,
        "op": op,
        "cluster": cluster,
        "selected_after": len(artifact.get("clusters") or []),
        "discarded_after": len(artifact.get("discarded") or []),
    }
    if reason:
        entry["reason"] = reason[:300]
    entry.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    run.setdefault("governance", []).append(entry)


def _ensure_baseline(run: dict) -> None:
    """Freeze the clusters artifact the pipeline produced, once, before the
    first edit lands.

    This exists for a specific failure: the deployed app is shared. One person
    discards a cluster to try the tools out, the next opens the same report and
    reads that edited selection as what the pipeline decided. Without a
    baseline there is no way to tell the two apart, or to get back.

    Snapshotting the artifact beats replaying the governance log backwards:
    the log records what happened, not the exact shape before it, and an
    inverted replay would have to be right about every op forever. A copy is
    right by construction.

    Taken BEFORE the mutation and only when absent, so it always holds the
    as-produced state no matter how many edits follow. Every caller is already
    inside the run lock.
    """
    if run.get("clusters_baseline") is not None:
        return
    stage = _clusters_stage(run)
    if stage is None:
        return
    run["clusters_baseline"] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "artifact": copy.deepcopy(stage.get("artifact") or {}),
    }


def _selection_changed(run: dict, run_id: str, what: str) -> None:
    """Every op that moves a cluster in or out invalidates the brief. Marked
    on the artefact synchronously (so the UI can say "updating"), rebuilt in
    the background so the op itself stays fast."""
    strategy_brief.mark_stale(run, what)


def _clusters_stage(run: dict) -> dict | None:
    for stage in run.get("stages", []):
        if stage["id"] == "clusters":
            return stage
    return None


def _match(entry: dict, name: str) -> bool:
    needle = name.strip().lower()
    if not needle:
        return False
    for field in ("name", "cluster_name", "head_term"):
        if str(entry.get(field, "")).strip().lower() == needle:
            return True
    return False


def _reasoning(entry: dict, decision: str) -> dict:
    """Gather every piece of reasoning attached to a cluster, under stable keys.

    The reasons were there but scattered across five differently-named fields
    among ~19 keys (discard_reason, selection_reason, rationale, seo_rationale,
    geo_rationale), so a caller had to know the schema to find them. An
    external agent should be able to read WHY a cluster was chosen or dropped
    without guessing.
    """
    block = {
        "decision": decision,
        "decision_reason": (
            entry.get("selection_reason") if decision == "selected"
            else entry.get("discard_reason")
        ) or "",
        # What it is and what to do with it — written where the business
        # context exists (selection), so a reader can act without the keywords.
        "what_it_is": entry.get("what_it_is") or "",
        "how_to_use_it": entry.get("how_to_use_it") or "",
        "why_these_keywords_group": entry.get("rationale") or "",
        "seo_rationale": entry.get("seo_rationale") or "",
        "geo_rationale": entry.get("geo_rationale") or "",
        # Measured, not modelled. The previous seo/geo/combined 0-100 scores
        # were LLM estimates of arithmetic it had the inputs to compute, and
        # they disagreed with the data (a 670-volume cluster outranked a
        # 4,360-volume one). They are surfaced only if an older run still
        # carries them, clearly separated from the measurements.
        "metrics": entry.get("metrics") or {},
        "opportunity": entry.get("opportunity"),
        "opportunity_rule": entry.get("opportunity_rule"),
    }
    if any(entry.get(f) is not None for f in ("seo_score", "geo_score", "combined_score")):
        block["legacy_model_scores"] = {
            "note": "Estimated by a model in an older run; prefer `metrics`.",
            "seo": entry.get("seo_score"),
            "geo": entry.get("geo_score"),
            "combined": entry.get("combined_score"),
        }
    return block


def _public_cluster(entry: dict, decision: str) -> dict:
    """One cluster in a shape a calling agent can rely on."""
    keywords = []
    for kw in entry.get("keywords") or []:
        if isinstance(kw, dict):
            keywords.append(kw)
        elif kw:
            keywords.append({"keyword": kw})
    return {
        "cluster_name": entry.get("cluster_name") or entry.get("name") or "",
        "head_term": entry.get("head_term") or "",
        "intent": entry.get("intent") or "",
        "keyword_count": len(keywords),
        "avg_volume": entry.get("avg_volume"),
        "avg_difficulty": entry.get("avg_difficulty"),
        "keywords": keywords,
        "reasoning": _reasoning(entry, decision),
        "proposed": bool(entry.get("proposed")),
        "promoted": bool(entry.get("promoted")),
        "refreshed": bool(entry.get("refreshed")),
    }


def list_clusters_all(run_id: str) -> dict | None:
    """Selected + discarded clusters for a run, each with its full reasoning."""
    run = runs.get_run(run_id)
    if run is None:
        return None
    stage = _clusters_stage(run)
    artifact = stage["artifact"] if stage else {}
    return {
        "run_id": run_id,
        "selection_made": bool(artifact.get("selected")),
        "note": (
            "Every cluster carries a `reasoning` block: decision_reason says why "
            "it was kept or dropped, why_these_keywords_group says why the "
            "keywords belong together, and seo/geo rationales explain the scores. "
            "Discarded clusters are parked, not deleted — promote them back with "
            "seo_promote_cluster."
        ),
        "selected": [_public_cluster(c, "selected") for c in artifact.get("clusters", [])],
        "discarded": [_public_cluster(c, "discarded") for c in artifact.get("discarded", [])],
    }


def promote_cluster(run_id: str, cluster_name: str, by: str = "agent") -> dict:
    """Move a discarded cluster back into the selection. Serialised per run."""
    with _run_lock(run_id):
        return _promote_cluster_locked(run_id, cluster_name, by)


def _promote_cluster_locked(run_id: str, cluster_name: str, by: str = "agent") -> dict:
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    stage = _clusters_stage(run)
    if stage is None:
        return {"ok": False, "error": "no clusters stage in this run"}
    _ensure_baseline(run)
    artifact = stage["artifact"]
    discarded = artifact.get("discarded", [])
    hit = next((c for c in discarded if _match(c, cluster_name)), None)
    if hit is None:
        return {"ok": False, "error": f"'{cluster_name}' not found among discarded clusters"}
    discarded.remove(hit)
    entry = dict(hit)
    entry.pop("discard_reason", None)
    entry["selection_reason"] = "Promoted back into the selection by the user."
    entry["promoted"] = True
    artifact.setdefault("clusters", []).append(entry)
    artifact["count"] = len(artifact["clusters"])
    # Logged AFTER the mutation: the entry records the state the change
    # produced, so selected_after must count the promoted cluster.
    _log_change(run, "promote", entry.get("cluster_name") or entry.get("name") or cluster_name,
                reason="promoted back into the selection", by=by,
                was_discarded_for=hit.get("discard_reason"))
    _selection_changed(run, run_id, f"promoted {entry.get('cluster_name') or cluster_name}")
    runs.save_run(run_id, run)
    strategy_brief.refresh_async(run_id)
    return {"ok": True, "promoted": entry.get("name"), "selected_count": artifact["count"]}


def discard_cluster(run_id: str, cluster_name: str, reason: str = "",
                    by: str = "agent") -> dict:
    """Move a selected cluster into the discarded set. Serialised per run."""
    with _run_lock(run_id):
        return _discard_cluster_locked(run_id, cluster_name, reason, by)


def _discard_cluster_locked(run_id: str, cluster_name: str, reason: str = "",
                            by: str = "agent") -> dict:
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    stage = _clusters_stage(run)
    if stage is None:
        return {"ok": False, "error": "no clusters stage in this run"}
    _ensure_baseline(run)
    artifact = stage["artifact"]
    clusters = artifact.get("clusters", [])
    hit = next((c for c in clusters if _match(c, cluster_name)), None)
    if hit is None:
        return {"ok": False, "error": f"'{cluster_name}' not found among selected clusters"}
    clusters.remove(hit)
    entry = dict(hit)
    entry["discard_reason"] = (reason or "discarded by user")[:300]
    entry["discarded_at"] = datetime.now(timezone.utc).isoformat()
    entry.pop("promoted", None)
    artifact.setdefault("discarded", []).append(entry)
    artifact["count"] = len(clusters)
    _log_change(run, "discard", entry.get("cluster_name") or entry.get("name") or cluster_name,
                reason=reason or "discarded by user", by=by)
    _selection_changed(run, run_id, f"discarded {entry.get('cluster_name') or cluster_name}")
    runs.save_run(run_id, run)
    strategy_brief.refresh_async(run_id)
    return {"ok": True, "discarded": entry.get("name"), "selected_count": len(clusters)}


def rerun_cluster_research(run_id: str, cluster_name: str) -> dict:
    """Re-run keyword research for ONE existing cluster, in place.

    The judge-facing move: "this cluster looks thin/wrong — go get fresh data
    for it" without re-running the whole pipeline or re-billing every other
    cluster. Re-seeds on the cluster's head term (one DataForSEO call,
    budget-accounted to the run) and merges any new keywords into that
    cluster with their real stats.
    """
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    stage = _clusters_stage(run)
    if stage is None:
        return {"ok": False, "error": "run has no clusters stage"}

    pools = {
        "selected": stage["artifact"].get("clusters") or [],
        "discarded": stage["artifact"].get("discarded") or [],
    }
    target = where = None
    for pool_name, entries in pools.items():
        for entry in entries:
            if _match(entry, cluster_name):
                target, where = entry, pool_name
                break
        if target:
            break
    if target is None:
        return {"ok": False, "error": f"cluster {cluster_name!r} not found in this run"}

    seed = (
        target.get("head_term")
        or (target.get("keywords") or [None])[0]
        or target.get("cluster_name")
        or target.get("name")
    )
    if isinstance(seed, dict):
        seed = seed.get("keyword")
    if not seed:
        return {"ok": False, "error": "cluster has no head term to re-seed from"}

    fresh = propose_cluster(run_id, str(seed))
    if not fresh.get("ok"):
        return fresh

    # propose_cluster appended a new cluster; fold it into the existing one
    # instead of leaving a near-duplicate beside it.
    run = runs.get_run(run_id)
    stage = _clusters_stage(run)
    entries = stage["artifact"].get(where) or []
    proposed = next(
        (e for e in (stage["artifact"].get("clusters") or []) if e.get("proposed")),
        None,
    )
    added = 0
    if proposed is not None:
        existing = {
            (k.get("keyword") if isinstance(k, dict) else k) for k in (target.get("keywords") or [])
        }
        merged = list(target.get("keywords") or [])
        for kw in proposed.get("keywords") or []:
            name = kw.get("keyword") if isinstance(kw, dict) else kw
            if name and name not in existing:
                existing.add(name)
                merged.append(kw)
                added += 1
        target["keywords"] = merged
        target["refreshed"] = True
        stage["artifact"]["clusters"] = [
            e for e in (stage["artifact"].get("clusters") or []) if e is not proposed
        ]
        for i, entry in enumerate(entries):
            if _match(entry, cluster_name):
                entries[i] = target
        stage["artifact"][where] = entries
        runs.save_run(run_id, run)

    return {
        "ok": True,
        "cluster_name": cluster_name,
        "pool": where,
        "seeded_from": seed,
        "keywords_added": added,
        "total_keywords": len(target.get("keywords") or []),
    }


def propose_cluster(
    run_id: str,
    topic: str,
    location_code: int | None = None,
    language_code: str | None = None,
    by: str = "agent",
) -> dict:
    """Propose a new cluster via a scoped re-seed on one topic.

    One DataForSEO keyword_suggestions call (budget-accounted to the run),
    then deterministic assembly: top suggestions become cluster members
    with their real volume/difficulty/intent/CPC stats.
    """
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "error": "topic is required"}
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}

    locale: dict = {}
    for stage in run.get("stages", []):
        if stage["id"] == "intake":
            locale = stage["artifact"].get("locale") or {}
    loc = location_code or locale.get("location_code") or 2840
    lang = language_code or locale.get("language_code") or "en"

    from .tools.dataforseo import keyword_suggestions

    with use_run(run_id):
        try:
            suggestions = keyword_suggestions(topic, limit=30, location_code=loc, language_code=lang)
        except Exception as e:
            return {"ok": False, "error": f"re-seed failed: {e}"}

    kws = sorted(
        (k for k in suggestions if isinstance(k, dict) and k.get("keyword")),
        key=lambda k: k.get("volume") or 0,
        reverse=True,
    )
    members = [topic] + [
        k["keyword"] for k in kws[:12]
        if k["keyword"].lower() != topic.lower()
    ]
    vols = [k["volume"] for k in kws[:12] if k.get("volume")]
    diffs = [k["difficulty"] for k in kws[:12] if k.get("difficulty")]
    intents = [k["intent"] for k in kws[:12] if k.get("intent")]

    # A proposed cluster joins the SELECTED set, so it has to arrive with the
    # same fields as one the pipeline produced. Observed 2026-09-01: a proposal
    # landed with no `cluster_name` and no reason, so the Run view showed a
    # nameless fourth pillar with an empty reasoning block sitting beside three
    # fully-justified ones. Whoever reads the strategy cannot tell where it
    # came from.
    #
    # `name` is kept as the model wrote it (often a long descriptive phrase);
    # `cluster_name` is a short label for display.
    label = topic.split("—")[0].split(" - ")[0].strip() or topic
    if len(label) > 48:
        label = label[:45].rstrip(" ,;:") + "…"

    entry = {
        "name": topic,
        "cluster_name": label,
        "head_term": topic,
        "keywords": members,
        "intent": max(set(intents), key=intents.count) if intents else "",
        "total_volume": sum(vols),
        "avg_difficulty": round(sum(diffs) / len(diffs)) if diffs else None,
        "market": market_label(loc, lang),
        "proposed": True,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        # Its own audit trail: this was added after the pipeline had chosen,
        # so it never went through score/select and must not look as if it did.
        "selection_reason": (
            f"Proposed after the pipeline ran, as a scoped keyword re-seed on "
            f"\"{topic}\". It did not go through the validation or selection "
            f"gates, so judge it on the {len(members)} keyword(s) below rather "
            f"than on a pipeline verdict."
        ),
        "seed_stats": kws[:12],
    }

    # Same read-modify-write hazard as promote/discard: take the run lock for
    # the mutating half. The DataForSEO call above is deliberately outside it,
    # so a slow network call cannot block other governance ops.
    with _run_lock(run_id):
        run = runs.get_run(run_id) or run
        stage = _clusters_stage(run)
        if stage is None:
            stage = {"id": "clusters", "label": "Clusters", "status": "done", "artifact": {}}
            run.setdefault("stages", []).append(stage)
        _ensure_baseline(run)
        artifact = stage["artifact"]
        existing = artifact.setdefault("clusters", [])
        if any(_match(c, topic) for c in existing):
            return {"ok": False, "error": f"a cluster for '{topic}' already exists"}
        existing.append(entry)
        artifact["count"] = len(existing)
        _log_change(run, "propose", entry.get("cluster_name") or topic,
                    reason=f"proposed and researched: {topic}", by=by,
                    keywords_found=len(members))
        _selection_changed(run, run_id, f"proposed {topic}")
        runs.save_run(run_id, run)
        strategy_brief.refresh_async(run_id)
    return {"ok": True, "proposed": entry}


def governance_history(run_id: str) -> dict:
    """How this strategy was shaped: every change, in order, and by whom."""
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    entries = run.get("governance") or []
    return {
        "ok": True,
        "run_id": run_id,
        "changes": entries,
        "count": len(entries),
        "note": (
            "Append-only record of promote/discard/propose operations. `by` "
            "says whether a change came from the agent, an external assistant "
            "over WebMCP, or the user. Empty means the pipeline's own output "
            "was never adjusted."
        ),
    }


def _changes_since_reset(run: dict) -> list[dict]:
    """Edits that are still standing.

    "Edited" has to mean "differs from what the pipeline produced", not "was
    ever touched" — otherwise a report stays flagged as modified forever after
    it has been put back, and the badge stops meaning anything. So the count
    runs from the last reset, and the earlier edits stay in the history where
    they belong.
    """
    history = run.get("governance") or []
    last_reset = max((i for i, e in enumerate(history) if e.get("op") == "reset"),
                     default=-1)
    return [e for e in history[last_reset + 1:] if e.get("op") != "reset"]


def change_state(run_id: str) -> dict:
    """Has this report been edited since the pipeline produced it?"""
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    entries = _changes_since_reset(run)
    return {
        "ok": True,
        "run_id": run_id,
        "edited": bool(entries),
        "change_count": len(entries),
        "can_reset": run.get("clusters_baseline") is not None,
        "last_change": entries[-1] if entries else None,
    }


def reset_run(run_id: str, by: str = "agent") -> dict:
    """Put the cluster selection back to what the pipeline produced.

    The reset is itself recorded rather than wiping the history: erasing the
    record of what someone tried is the opposite of what a governance log is
    for, and the next reader still deserves to know an edit happened and was
    undone. Idempotent — resetting an unedited run is a no-op.
    """
    with _run_lock(run_id):
        run = runs.get_run(run_id)
        if run is None:
            return {"ok": False, "error": "run not found"}
        baseline = run.get("clusters_baseline")
        if not baseline:
            return {"ok": False, "error": "this run has never been edited, so there is nothing to undo"}
        stage = _clusters_stage(run)
        if stage is None:
            return {"ok": False, "error": "no clusters stage in this run"}

        undone = len(_changes_since_reset(run))
        stage["artifact"] = copy.deepcopy(baseline["artifact"])
        _log_change(run, "reset", "(whole selection)",
                    reason=f"restored the {undone} change(s) back to as-produced", by=by,
                    changes_undone=undone)
        _selection_changed(run, run_id, "reset to as-produced")
        runs.save_run(run_id, run)
        strategy_brief.refresh_async(run_id)
        artifact = stage["artifact"]
        return {
            "ok": True,
            "run_id": run_id,
            "changes_undone": undone,
            "selected_count": len(artifact.get("clusters") or []),
            "discarded_count": len(artifact.get("discarded") or []),
            "note": ("The selection is back to what the pipeline produced. The "
                     "history of what was changed is kept, including this reset."),
        }
