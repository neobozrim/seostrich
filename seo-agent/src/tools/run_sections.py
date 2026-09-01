"""Let the agent read its own run — from the stages, which already hold it.

Tool results are capped at 4,000 characters and the graphs produce far more, so
the agent needs a way to pull what it decides it needs.

An earlier version of this wrote a SECOND copy of each result to its own file.
That was duplication: the pipeline already records every node's output as a
stage (measured on a real run: 39,121 characters across six stages, and the
same keyword stats appearing in two places). One store, addressed by stage.
"""
from __future__ import annotations

import json
from typing import Any

from .. import pipeline_recorder as rec
from .. import runs as runs_store

# Comfortably under the 4,000-char tool-result cap, leaving room for the
# wrapper fields.
PAGE = 3000


def stage_manifest(run_id: str = "") -> dict:
    """What this run holds, and how big each part is."""
    rid = run_id or rec.active_run_id() or ""
    run = runs_store.get_run(rid) if rid else None
    if not run:
        return {"error": "no active run"}
    stages = []
    for stage in run.get("stages", []):
        artifact = stage.get("artifact") or {}
        text = json.dumps(artifact, ensure_ascii=False, default=str)
        stages.append({
            "stage": stage.get("id"),
            "label": stage.get("label"),
            "chars": len(text),
            "pages": max(1, (len(text) + PAGE - 1) // PAGE),
            "sections": sorted(artifact) if isinstance(artifact, dict) else [],
        })
    return {"run_id": rid, "stages": stages}


def read_run_section(
    stage: str = "",
    section: str = "",
    page: int = 1,
    run_id: str = "",
) -> dict:
    """Read part of a recorded stage. Paged, so nothing is ever truncated.

    stage:   e.g. 'clusters', 'pillars', 'ai_citability', 'keywords'.
             Omit to list the stages this run holds.
    section: a key inside that stage's artifact, e.g. 'brief' or 'discarded'.
             Omit to list the sections and their sizes.
    page:    1-based; the reply says whether more pages follow.
    """
    rid = run_id or rec.active_run_id() or ""
    if not rid:
        return {"error": "no active run; pass run_id explicitly"}
    run = runs_store.get_run(rid)
    if not run:
        return {"error": f"run {rid} not found"}

    if not stage:
        return stage_manifest(rid)

    found = next((s for s in run.get("stages", []) if s.get("id") == stage), None)
    if found is None:
        return {
            "error": f"no stage '{stage}' in this run",
            "available": [s.get("id") for s in run.get("stages", [])],
        }

    artifact = found.get("artifact") or {}
    if not section:
        return {
            "stage": stage,
            "sections": [
                {"section": k,
                 "chars": len(json.dumps(v, ensure_ascii=False, default=str))}
                for k, v in (artifact.items() if isinstance(artifact, dict) else [])
            ],
            "hint": "call again with section= to read one, page= to continue it",
        }

    if not isinstance(artifact, dict) or section not in artifact:
        return {
            "error": f"no section '{section}' in stage '{stage}'",
            "available": list(artifact) if isinstance(artifact, dict) else [],
        }

    text = json.dumps(artifact[section], ensure_ascii=False, indent=2, default=str)
    pages = max(1, (len(text) + PAGE - 1) // PAGE)
    page = max(1, min(page, pages))
    start = (page - 1) * PAGE
    chunk = text[start:start + PAGE]

    out: dict[str, Any] = {
        "stage": stage,
        "section": section,
        "page": page,
        "of_pages": pages,
        "more": page < pages,
        "content": chunk,
    }
    if page < pages:
        out["next"] = (
            f"read_run_section(stage='{stage}', section='{section}', page={page + 1})"
        )
    return out
