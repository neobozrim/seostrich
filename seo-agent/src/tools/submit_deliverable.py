"""Record an agent-synthesized deliverable as a pipeline stage.

Some pipeline outputs are not the direct result of a single tool call —
the agent synthesizes them (an on-page brief, an AI-citability brief).
This tool lets the agent submit those so the Run view shows them as
first-class stages instead of burying them in chat text.
"""
from __future__ import annotations

from .. import llm, pipeline_recorder

ALLOWED_STAGES = (
    "intake", "seeds", "keywords", "clusters", "pillars", "mix",
    "audit", "competitors", "onpage", "ai_citability",
)


def submit_deliverable(stage_id: str, title: str, artifact) -> dict:
    """Submit a finished deliverable so it is recorded in the active run.

    Args:
        stage_id: which pipeline stage this deliverable belongs to
        title: short human-readable title for the deliverable
        artifact: the deliverable content as a JSON object
    """
    if stage_id not in ALLOWED_STAGES:
        return {
            "status": "rejected",
            "message": f"Unknown stage '{stage_id}'. Allowed: {', '.join(ALLOWED_STAGES)}",
        }

    if isinstance(artifact, str):
        try:
            artifact = llm.extract_json(artifact)
        except (ValueError, TypeError):
            artifact = {"content": artifact}
    if not isinstance(artifact, dict) or not artifact:
        return {"status": "rejected", "message": "artifact must be a non-empty object"}

    run_id = pipeline_recorder.active_run_id()
    if run_id is None:
        return {
            "status": "rejected",
            "message": "No active pipeline run — deliverables can only be recorded inside a chat pipeline run",
        }

    pipeline_recorder.record_deliverable(stage_id, str(title or stage_id), artifact)
    return {"status": "recorded", "stage_id": stage_id, "run_id": run_id, "title": str(title or stage_id)}
