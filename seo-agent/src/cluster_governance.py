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

from datetime import datetime, timezone

from . import runs
from .pipeline_recorder import market_label, use_run


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


def list_clusters_all(run_id: str) -> dict | None:
    """Selected + discarded clusters for a run (None if the run is missing)."""
    run = runs.get_run(run_id)
    if run is None:
        return None
    stage = _clusters_stage(run)
    artifact = stage["artifact"] if stage else {}
    return {
        "run_id": run_id,
        "selection_made": bool(artifact.get("selected")),
        "selected": artifact.get("clusters", []),
        "discarded": artifact.get("discarded", []),
    }


def promote_cluster(run_id: str, cluster_name: str) -> dict:
    """Move a discarded cluster back into the selection."""
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    stage = _clusters_stage(run)
    if stage is None:
        return {"ok": False, "error": "no clusters stage in this run"}
    artifact = stage["artifact"]
    discarded = artifact.get("discarded", [])
    hit = next((c for c in discarded if _match(c, cluster_name)), None)
    if hit is None:
        return {"ok": False, "error": f"'{cluster_name}' not found among discarded clusters"}
    discarded.remove(hit)
    entry = dict(hit)
    entry.pop("discard_reason", None)
    entry["promoted"] = True
    artifact.setdefault("clusters", []).append(entry)
    artifact["count"] = len(artifact["clusters"])
    runs.save_run(run_id, run)
    return {"ok": True, "promoted": entry.get("name"), "selected_count": artifact["count"]}


def discard_cluster(run_id: str, cluster_name: str, reason: str = "") -> dict:
    """Move a selected cluster into the discarded set (keeps its stats)."""
    run = runs.get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run not found"}
    stage = _clusters_stage(run)
    if stage is None:
        return {"ok": False, "error": "no clusters stage in this run"}
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
    runs.save_run(run_id, run)
    return {"ok": True, "discarded": entry.get("name"), "selected_count": len(clusters)}


def propose_cluster(
    run_id: str,
    topic: str,
    location_code: int | None = None,
    language_code: str | None = None,
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

    entry = {
        "name": topic,
        "head_term": topic,
        "keywords": members,
        "intent": max(set(intents), key=intents.count) if intents else "",
        "total_volume": sum(vols),
        "avg_difficulty": round(sum(diffs) / len(diffs)) if diffs else None,
        "market": market_label(loc, lang),
        "proposed": True,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "seed_stats": kws[:12],
    }

    stage = _clusters_stage(run)
    if stage is None:
        stage = {"id": "clusters", "label": "Clusters", "status": "done", "artifact": {}}
        run.setdefault("stages", []).append(stage)
    artifact = stage["artifact"]
    existing = artifact.setdefault("clusters", [])
    if any(_match(c, topic) for c in existing):
        return {"ok": False, "error": f"a cluster for '{topic}' already exists"}
    existing.append(entry)
    artifact["count"] = len(existing)
    runs.save_run(run_id, run)
    return {"ok": True, "proposed": entry}
