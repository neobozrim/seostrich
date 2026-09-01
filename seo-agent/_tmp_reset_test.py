"""Reset-to-as-produced: the multi-judge safety net.

The scenario this protects: the deployed app is shared. One person edits a
report to try the tools, the next reads that edited selection as the
pipeline's own verdict. These assertions cover the baseline being the
AS-PRODUCED state (not the state before the most recent edit), the reset being
honest about itself, and the history surviving.
"""
import copy

from src import cluster_governance as g
from src import runs

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


def fresh(run_id="test-reset-run"):
    run = {
        "id": run_id,
        "title": "reset",
        "project": "t",
        "stages": [{
            "id": "clusters", "label": "Clusters", "status": "done",
            "artifact": {
                "clusters": [
                    {"name": "a", "cluster_name": "Alpha", "head_term": "a"},
                    {"name": "b", "cluster_name": "Beta", "head_term": "b"},
                    {"name": "c", "cluster_name": "Gamma", "head_term": "c"},
                ],
                "discarded": [
                    {"name": "d", "cluster_name": "Delta", "head_term": "d",
                     "discard_reason": "off topic"},
                ],
                "count": 3,
            },
        }],
    }
    runs.save_run(run_id, run)
    return run_id


rid = fresh()

# --- untouched runs report themselves as untouched --------------------------
st = g.change_state(rid)
ok(st["edited"] is False, "a fresh run is not edited")
ok(st["change_count"] == 0, "a fresh run has no changes")
ok(st["can_reset"] is False, "nothing to reset before the first edit")
ok(g.reset_run(rid)["ok"] is False, "reset refuses when nothing was edited")

# --- first edit captures the baseline ---------------------------------------
g.discard_cluster(rid, "Alpha", "judge A does not like it", by="judge-a")
run = runs.get_run(rid)
base = run.get("clusters_baseline")
ok(base is not None, "the first edit captures a baseline")
ok(len(base["artifact"]["clusters"]) == 3, "the baseline holds the AS-PRODUCED 3 clusters")
ok(len(runs.get_run(rid)["stages"][0]["artifact"]["clusters"]) == 2, "the live artifact has 2")

st = g.change_state(rid)
ok(st["edited"] is True and st["change_count"] == 1, "one change is visible")
ok(st["can_reset"] is True, "reset is now offered")
ok(st["last_change"]["by"] == "judge-a", "the last change names who made it")

# --- more edits do NOT move the baseline ------------------------------------
g.discard_cluster(rid, "Beta", "judge B disagrees too", by="judge-b")
g.promote_cluster(rid, "Delta", by="judge-b")
base2 = runs.get_run(rid)["clusters_baseline"]
ok(base2["captured_at"] == base["captured_at"], "the baseline is captured once, not per edit")
ok(len(base2["artifact"]["clusters"]) == 3, "the baseline is still the as-produced state")
ok(g.change_state(rid)["change_count"] == 3, "three changes recorded")

live = runs.get_run(rid)["stages"][0]["artifact"]
ok(len(live["clusters"]) == 2, "live selection drifted to 2 (Gamma + promoted Delta)")

# --- the reset ---------------------------------------------------------------
res = g.reset_run(rid, by="judge-c")
ok(res["ok"] is True, "reset succeeds once edited")
ok(res["changes_undone"] == 3, "reset reports how many changes it undid")

live = runs.get_run(rid)["stages"][0]["artifact"]
ok([c["name"] for c in live["clusters"]] == ["a", "b", "c"], "all three clusters are back, in order")
ok([c["name"] for c in live["discarded"]] == ["d"], "the discarded set is back too")
ok(live["discarded"][0]["discard_reason"] == "off topic", "the original discard reason survived")
ok("promoted" not in live["clusters"][0], "no edit residue on the restored entries")

# --- the reset is recorded, not a memory hole -------------------------------
hist = g.governance_history(rid)["changes"]
ok(len(hist) == 4, "the reset is itself an entry (3 edits + 1 reset)")
ok(hist[-1]["op"] == "reset", "the last entry is the reset")
ok(hist[-1]["by"] == "judge-c", "the reset names who did it")
ok(hist[0]["op"] == "discard" and hist[0]["by"] == "judge-a",
   "the undone edits are still in the record")

st = g.change_state(rid)
ok(st["edited"] is False, "after a reset the report reads as unedited again")
ok(st["change_count"] == 0, "the reset itself is not counted as an edit")
ok(st["can_reset"] is True, "the baseline is kept, so a later edit can be undone again")

# --- restoring a deep copy, not a shared reference --------------------------
g.discard_cluster(rid, "Alpha", "again", by="judge-d")
live = runs.get_run(rid)["stages"][0]["artifact"]
ok(len(live["clusters"]) == 2, "a post-reset edit still works")
ok(len(runs.get_run(rid)["clusters_baseline"]["artifact"]["clusters"]) == 3,
   "editing after a reset did not corrupt the baseline through a shared reference")
g.reset_run(rid, by="judge-d")
ok(len(runs.get_run(rid)["stages"][0]["artifact"]["clusters"]) == 3, "second reset works")

# --- a run with no clusters stage doesn't explode ---------------------------
runs.save_run("test-reset-empty", {"id": "test-reset-empty", "stages": []})
ok(g.change_state("test-reset-empty")["edited"] is False, "a stageless run reads as unedited")
ok(g.reset_run("test-reset-empty")["ok"] is False, "reset declines a stageless run")
ok(g.change_state("test-reset-missing-entirely")["ok"] is False, "an unknown run is an error")

print(f"reset: {PASS} assertions passed")
