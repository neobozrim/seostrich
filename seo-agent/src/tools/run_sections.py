"""Let the agent read its own run, instead of being handed someone's summary.

Tool results are capped at 4,000 characters, and the strategy and GEO graphs
return far more than that. The first attempt at solving this was a projection
that picked "the important fields" — which bakes one person's guess about what
matters into the agent's only view of its own work, and then tells it not to
ask for more. If the agent needs something the projection dropped, it is stuck,
precisely at the step where judgement matters.

So: the graph writes its FULL result to disk, returns a manifest of what exists,
and the agent reads whatever it decides it needs, in pages. Nothing is
discarded, nothing is pre-judged, and a long result costs several small reads
instead of one truncated one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import pipeline_recorder as rec
from .. import runs as runs_store

# Comfortably under the 4,000-char tool-result cap, leaving room for the
# wrapper fields.
PAGE = 3000


def _artifacts_dir() -> Path:
    from .. import memory

    path = memory._get_memory_dir() / "run-artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_full_result(run_id: str, name: str, payload: Any) -> dict:
    """Persist a graph's complete output next to the run, and describe it.

    Returns the manifest entry: what it is, how big, and how to read it.
    """
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in f"{run_id}-{name}")
    path = _artifacts_dir() / f"{safe}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")

    sections = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            size = len(json.dumps(value, ensure_ascii=False, default=str))
            sections.append({
                "section": key,
                "chars": size,
                "pages": max(1, (size + PAGE - 1) // PAGE),
            })
        sections.sort(key=lambda s: s["chars"], reverse=True)

    return {
        "artifact": name,
        "total_chars": len(text),
        "sections": sections[:20],
    }


def read_run_section(
    name: str,
    section: str = "",
    page: int = 1,
    run_id: str = "",
) -> dict:
    """Read part of a graph's full output. Paged, so nothing is ever truncated.

    name:    the artifact name from the manifest (e.g. "geo_demand").
    section: a top-level key such as "brief" or "ranked". Omit for the list of
             sections with their sizes.
    page:    1-based; the response says whether more pages follow.
    """
    rid = run_id or rec.active_run_id() or ""
    if not rid:
        return {"error": "no active run; pass run_id explicitly"}

    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in f"{rid}-{name}")
    path = _artifacts_dir() / f"{safe}.json"
    if not path.exists():
        available = sorted(p.stem for p in _artifacts_dir().glob(f"*{rid}*"))
        return {"error": f"no artifact '{name}' for this run", "available": available}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"could not read artifact: {exc}"}

    if not section:
        return {
            "artifact": name,
            "sections": [
                {
                    "section": k,
                    "chars": len(json.dumps(v, ensure_ascii=False, default=str)),
                }
                for k, v in (payload.items() if isinstance(payload, dict) else [])
            ],
            "hint": "call again with section= to read one, page= to continue it",
        }

    if not isinstance(payload, dict) or section not in payload:
        return {
            "error": f"no section '{section}'",
            "available": list(payload) if isinstance(payload, dict) else [],
        }

    text = json.dumps(payload[section], ensure_ascii=False, indent=2, default=str)
    pages = max(1, (len(text) + PAGE - 1) // PAGE)
    page = max(1, min(page, pages))
    start = (page - 1) * PAGE
    chunk = text[start:start + PAGE]

    return {
        "artifact": name,
        "section": section,
        "page": page,
        "of_pages": pages,
        "more": page < pages,
        "content": chunk,
        **({"next": f"read_run_section(name='{name}', section='{section}', page={page + 1})"}
           if page < pages else {}),
    }
