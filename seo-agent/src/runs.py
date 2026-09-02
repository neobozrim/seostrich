"""Run artifacts — structured pipeline output for the Run/Pipeline view.

A *run* is a project's full SEO pipeline captured as an ordered list of stages,
each with an artifact (intake → seeds → keywords → clusters → pillars → mix).

Runs live in <memory_dir>/runs/<id>.json so they share the single blackboard.
Default/example runs are seeded from the repo's seed/runs/ directory and can be
restored at any time (restore-default).
"""
from __future__ import annotations

import hashlib
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


# A run id becomes a file name. Every run id the API sees comes from a URL
# path segment, so without this "../../seed/runs/productpirates" reads or
# OVERWRITES a .json file anywhere the process can reach. The ids the app
# itself mints are slugs of this shape; anything else is rejected before it
# touches the filesystem.
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _valid_id(run_id: str) -> bool:
    return bool(run_id) and bool(_RUN_ID.match(run_id)) and ".." not in run_id


def _run_path(run_id: str) -> Path:
    if not _valid_id(run_id):
        raise ValueError(f"invalid run id: {run_id!r}")
    return _runs_dir() / f"{run_id}.json"


def _flow_of(run: dict) -> str:
    """What kind of report this is, from the stages it holds (the same rule
    the report view uses for its tag)."""
    ids = {s.get("id") for s in run.get("stages", []) if isinstance(s, dict)}
    if "ai_citability" in ids and not ({"clusters", "seeds"} & ids):
        return "AI visibility"
    if {"pillars", "clusters", "keywords", "seeds"} & ids:
        return "SEO content strategy"
    if "audit" in ids:
        return "Technical audit"
    return ""


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
                    "flow": _flow_of(run),
                    "modified": path.stat().st_mtime,
                    # Pinned runs lead the home canvas regardless of recency,
                    # so a curated run stays the first thing anyone sees.
                    "pinned": bool(run.get("pinned")),
                    "archived": bool(run.get("archived")),
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
    if not _valid_id(run_id):
        return None
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
    if not _valid_id(run_id):
        return False
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


# Not "*.json": list_runs() globs "*.json" in the runs dir, so a marker with
# that extension would show up on the canvas as a report.
_SEED_MARKER = ".seeds-installed"


def sync_seeds() -> list[str]:
    """Install every bundled report whose seed file changed since it was last
    installed. Returns the ids written.

    Runs at startup. The rule is deliberately NOT "copy on every start": the
    process restarts on every deploy, and that would wipe a judge's
    in-progress edits each time a commit lands. Instead each seed's content
    hash is remembered when it is installed, and a seed is re-copied only when
    that hash changes — i.e. when a new version of the fixture ships. Edits
    made to the live copy survive restarts until the fixture itself is
    updated, which is exactly when they should be replaced.

    A seed whose live copy has gone missing is reinstalled regardless.
    """
    seed_dir = _seed_dir()
    if not seed_dir.exists():
        return []
    runs_dir = _runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    marker = runs_dir / _SEED_MARKER
    try:
        installed = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    except (OSError, ValueError):
        installed = {}

    written = []
    for path in sorted(seed_dir.glob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target = runs_dir / path.name
        if installed.get(path.name) == digest and target.exists():
            continue
        shutil.copyfile(path, target)
        installed[path.name] = digest
        written.append(path.stem)

    if written:
        marker.write_text(json.dumps(installed, indent=2), encoding="utf-8")
    return written


def restore_defaults() -> list[str]:
    """Force-reseed all default runs from the repo seed dir."""
    return seed_defaults(force=True)


def set_archived(run_id: str, archived: bool) -> dict | None:
    """Archived runs leave the home canvas for the Archive folder. Nothing is
    deleted; an archived run is unpinned, since pinned means "show first"."""
    run = get_run(run_id)
    if run is None:
        return None
    run["archived"] = bool(archived)
    if archived:
        run["pinned"] = False
    save_run(run_id, run)
    return run


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
