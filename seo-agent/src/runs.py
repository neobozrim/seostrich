"""Run artifacts — structured pipeline output for the Run/Pipeline view.

A *run* is a project's full SEO pipeline captured as an ordered list of stages,
each with an artifact (intake → seeds → keywords → clusters → pillars → mix).

Runs live in <memory_dir>/runs/<id>.json so they share the single blackboard.
Default/example runs are seeded from the repo's seed/runs/ directory and can be
restored at any time (restore-default).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import memory

_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _runs_dir() -> Path:
    d = memory._get_memory_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seed_dir() -> Path:
    # src/runs.py -> src/ -> seo-agent/ -> seed/runs/
    return Path(__file__).resolve().parent.parent / "seed" / "runs"


def _valid_run_id(run_id: str) -> bool:
    return bool(run_id) and _RUN_ID_RE.match(run_id) is not None


def _run_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def list_runs() -> list[dict]:
    """Return summaries for every stored run, newest first."""
    summaries = []
    for path in sorted(_runs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
            summaries.append(
                {
                    "id": run.get("id", path.stem),
                    "project": run.get("project"),
                    "title": run.get("title"),
                    "created": run.get("created"),
                    "status": run.get("status"),
                    "stages": len(run.get("stages", [])),
                    "modified": path.stat().st_mtime,
                    # Pinned runs lead the home canvas regardless of recency,
                    # so a curated run stays the first thing anyone sees.
                    "pinned": bool(run.get("pinned")),
                    "pin_note": run.get("pin_note") or "",
                }
            )
        except Exception:
            continue
    # Pinned first, then newest. Sorting here rather than in the UI keeps every
    # consumer (canvas, RunView, WebMCP) in the same order.
    summaries.sort(key=lambda r: (not r["pinned"], -(r["modified"] or 0)))
    return summaries


def get_run(run_id: str) -> dict | None:
    if not _valid_run_id(run_id):
        return None
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_run(run_id: str, run: dict) -> bool:
    if not _valid_run_id(run_id):
        return False
    path = _run_path(run_id)
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def add_feedback(run_id: str, text: str, author: str = "judge") -> dict | None:
    """Append a feedback entry to a run. Returns the updated run."""
    run = get_run(run_id)
    if run is None:
        return None
    from datetime import datetime, timezone

    run.setdefault("feedback", []).append(
        {
            "text": text,
            "author": author,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_run(run_id, run)
    return run


def seed_defaults(force: bool = False) -> list[str]:
    """Copy seed runs into the live runs dir. Returns ids written.

    With force=False only seeds when the live runs dir is empty.
    """
    written = []
    seed_dir = _seed_dir()
    if not seed_dir.exists():
        return written

    runs_dir = _runs_dir()
    has_live = any(runs_dir.glob("*.json"))
    if has_live and not force:
        return written

    for path in seed_dir.glob("*.json"):
        target = runs_dir / path.name
        if target.exists() and not force:
            continue
        shutil.copyfile(path, target)
        written.append(path.stem)
    return written


def restore_defaults() -> list[str]:
    """Force-reseed all default runs from the repo seed dir."""
    return seed_defaults(force=True)


def set_pinned(run_id: str, pinned: bool, note: str = "") -> dict | None:
    """Pin or unpin a run. Pinned runs lead the home canvas."""
    run = get_run(run_id)
    if run is None:
        return None
    run["pinned"] = bool(pinned)
    if pinned:
        run["pin_note"] = note or run.get("pin_note") or ""
    else:
        run.pop("pin_note", None)
    save_run(run_id, run)
    return {"id": run_id, "pinned": run["pinned"], "pin_note": run.get("pin_note", "")}
