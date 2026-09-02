"""Governance ops must not lose each other's writes.

The agent dispatches tool calls in PARALLEL. Every governance op is
read-run -> mutate -> save-whole-run, so without serialisation two concurrent
calls read the same state and the second write erases the first.

Observed 2026-09-01: seven promote/discard/propose calls at one timestamp, and
the agent reported its discard had been "backfilled into the selection" — it
was watching its own change get overwritten, and spent extra rounds re-applying
it.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src import cluster_governance as gov
from src import runs as runs_store

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RID = "test-race-run"
NAMES = [f"C{i}" for i in range(8)]


def fixture():
    runs_store.save_run(RID, {
        "id": RID, "project": "t", "title": "race", "status": "done",
        "stages": [{"id": "clusters", "label": "Clusters", "status": "done", "artifact": {
            "selected": True,
            "clusters": [{"name": n, "cluster_name": n, "keywords": [f"{n}-kw"]} for n in NAMES],
            "discarded": [],
        }}],
    })


print("1. concurrent discards all land")
fixture()
errors: list = []


def discard(name):
    try:
        gov.discard_cluster(RID, name, f"discarding {name}")
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)


threads = [threading.Thread(target=discard, args=(n,)) for n in NAMES[:6]]
for t in threads:
    t.start()
for t in threads:
    t.join()

state = gov.list_clusters_all(RID)
discarded = {c["cluster_name"] for c in state["discarded"]}
selected = {c["cluster_name"] for c in state["selected"]}
chk("no exceptions", not errors, str(errors[:2]))
chk("all six discards survived", discarded == set(NAMES[:6]),
    f"discarded={sorted(discarded)}")
chk("the untouched two are still selected", selected == set(NAMES[6:]),
    f"selected={sorted(selected)}")
chk("nothing was lost or duplicated",
    len(state["selected"]) + len(state["discarded"]) == len(NAMES),
    f"{len(state['selected'])}+{len(state['discarded'])}")

print("2. concurrent discard + promote do not undo each other")
fixture()
gov.discard_cluster(RID, "C7", "parked")
threads = [
    threading.Thread(target=gov.discard_cluster, args=(RID, "C0", "out")),
    threading.Thread(target=gov.discard_cluster, args=(RID, "C1", "out")),
    threading.Thread(target=gov.promote_cluster, args=(RID, "C7")),
]
for t in threads:
    t.start()
for t in threads:
    t.join()

state = gov.list_clusters_all(RID)
selected = {c["cluster_name"] for c in state["selected"]}
discarded = {c["cluster_name"] for c in state["discarded"]}
chk("both discards held", {"C0", "C1"} <= discarded, f"discarded={sorted(discarded)}")
chk("the promote held", "C7" in selected, f"selected={sorted(selected)}")
chk("no cluster is in both sets", not (selected & discarded),
    str(selected & discarded))
chk("total is still eight", len(selected) + len(discarded) == len(NAMES),
    f"{len(selected)}+{len(discarded)}")

print("3. the lock is per run, not global")
chk("distinct runs get distinct locks",
    gov._run_lock("run-a") is not gov._run_lock("run-b"))
chk("same run reuses its lock", gov._run_lock("run-a") is gov._run_lock("run-a"))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
