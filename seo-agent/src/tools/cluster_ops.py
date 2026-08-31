"""Chat-facing cluster governance tools (thin wrappers over cluster_governance).

These operate on the run active in the current chat session, so the user
can say "promote the pricing cluster back" or "discard X, it overlaps"
right after a pipeline run. The same operations are exposed over REST for
WebMCP clients.
"""
from __future__ import annotations

from .. import cluster_governance, pipeline_recorder


def _run_id() -> str | None:
    return pipeline_recorder.active_run_id()


def list_clusters_all() -> dict:
    """List selected AND discarded clusters of the active run (with stats and discard reasons)."""
    run_id = _run_id()
    if not run_id:
        return {"ok": False, "error": "no active pipeline run"}
    return cluster_governance.list_clusters_all(run_id) or {"ok": False, "error": "run not found"}


def promote_cluster(cluster_name: str) -> dict:
    """Promote a previously discarded cluster back into the selection."""
    run_id = _run_id()
    if not run_id:
        return {"ok": False, "error": "no active pipeline run"}
    return cluster_governance.promote_cluster(run_id, cluster_name)


def discard_cluster(cluster_name: str, reason: str = "") -> dict:
    """Discard a selected cluster (moves it to the discarded set, stats preserved)."""
    run_id = _run_id()
    if not run_id:
        return {"ok": False, "error": "no active pipeline run"}
    return cluster_governance.discard_cluster(run_id, cluster_name, reason)


def propose_cluster(topic: str) -> dict:
    """Propose a new cluster for the active run via a scoped keyword re-seed on one topic."""
    run_id = _run_id()
    if not run_id:
        return {"ok": False, "error": "no active pipeline run"}
    return cluster_governance.propose_cluster(run_id, topic)
