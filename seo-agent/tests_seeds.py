"""Bundled reports install themselves — but only when they change.

The process restarts on every deploy. If seeds were copied on every start, a
judge's in-progress edits on the pinned report would vanish each time a
commit landed. So a seed is installed when it is new, missing, or its content
changed — and left alone otherwise.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

tmp = Path(tempfile.mkdtemp(prefix="seo-seeds-"))
seed_dir = tmp / "seed"
runs_dir = tmp / "runs"
seed_dir.mkdir()
os.environ["SESSIONS_DIR"] = str(tmp)

from src import runs  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


def seed(name, payload):
    (seed_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def live(name):
    return json.loads((runs_dir / f"{name}.json").read_text(encoding="utf-8"))


with patch.object(runs, "_seed_dir", lambda: seed_dir), patch.object(runs, "_runs_dir", lambda: runs_dir):
    # 1. fresh install
    seed("pirates", {"id": "pirates", "title": "v1", "stages": [], "pinned": True})
    ok(runs.sync_seeds() == ["pirates"], "a new seed is installed on first start")
    ok(live("pirates")["title"] == "v1", "the live copy is the seed")

    # 2. restart: nothing changed, nothing copied
    ok(runs.sync_seeds() == [], "an unchanged seed is not re-copied on restart")

    # 3. a judge edits the live copy; a restart must not undo them
    d = live("pirates")
    d["title"] = "edited by a judge"
    d["governance"] = [{"op": "discard"}]
    runs.save_run("pirates", d)
    ok(runs.sync_seeds() == [], "restart after a judge edit copies nothing")
    ok(live("pirates")["title"] == "edited by a judge", "the judge's edit survives the restart")

    # 4. a new fixture version ships — THAT replaces the live copy
    seed("pirates", {"id": "pirates", "title": "v2", "stages": [], "pinned": True})
    ok(runs.sync_seeds() == ["pirates"], "a changed seed is reinstalled")
    ok(live("pirates")["title"] == "v2", "the new fixture version wins over the edit")
    ok("governance" not in live("pirates"), "the edit history went with the old version")

    # 5. a second fixture arrives; only it is written
    seed("braintrust", {"id": "braintrust", "title": "b1", "stages": []})
    ok(runs.sync_seeds() == ["braintrust"], "only the new seed is written, the other is untouched")
    ok(live("pirates")["title"] == "v2", "pirates untouched by braintrust arriving")

    # 6. a live copy deleted by hand comes back
    (runs_dir / "braintrust.json").unlink()
    ok(runs.sync_seeds() == ["braintrust"], "a missing live copy is reinstalled")

    # 7. the marker is not a report
    ids = [r["id"] for r in runs.list_runs()]
    ok(".seeds-installed" not in ids and not any("seeds-installed" in i for i in ids),
       "the install marker never shows up on the canvas")
    ok(sorted(ids) == ["braintrust", "pirates"], f"only the two reports are listed, got {ids}")

    # 8. restore_defaults still force-copies everything, for the manual path
    d = live("pirates"); d["title"] = "edited again"; runs.save_run("pirates", d)
    ok(sorted(runs.restore_defaults()) == ["braintrust", "pirates"], "restore-defaults copies all seeds")
    ok(live("pirates")["title"] == "v2", "restore-defaults undid the edit")

print(f"seeds: {PASS} assertions passed")
