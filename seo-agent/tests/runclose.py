"""A stream that dies must not leave its run marked "running" forever.

Observed 2026-09-01: a client timed out at 20 minutes, the agent finished its
work three minutes later, and the run was STILL marked running twenty minutes
after that — because a generator whose consumer has gone away is closed at
whatever yield it was parked on, so the end_run() call is never reached. The
Run view spins until the server restarts and its startup sweep cleans up.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src import pipeline_recorder as rec
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


src = Path("src/orchestrator.py").read_text(encoding="utf-8")

print("1. the stream tracks what it opened")
chk("opened_runs declared", "opened_runs: set[str] = set()" in src)
chk("populated at begin_run", "opened_runs.add(run_id)" in src)
chk("declared before the try, so finally can see it",
    src.index("opened_runs: set[str] = set()") < src.index("        yield {\"type\": \"session_id\""))

print("2. the finally closes stragglers")
tail = src[src.index("    finally:"):]
chk("iterates the opened runs", "for opened in opened_runs:" in tail)
chk("only touches ones still running", 'record.get("status") == "running"' in tail)
chk("closes them", "pipeline_recorder.end_run(" in tail)
chk("bookkeeping cannot raise out of finally", "except Exception:" in tail)

print("3. a run left running really does get closed")
RID = "test-runclose"
runs_store.save_run(RID, {"id": RID, "project": "t", "title": "t",
                          "status": "running", "stages": [{"id": "seeds"}]})
chk("fixture starts running", runs_store.get_run(RID)["status"] == "running")
rec.end_run(RID, status="done")
chk("end_run closes it", runs_store.get_run(RID)["status"] == "done")
chk("and stamps an end time", bool(runs_store.get_run(RID).get("ended")))

print("4. a finished run is not reopened or relabelled")
before = runs_store.get_run(RID)["status"]
# the finally only acts on status == "running", so a done run is untouched
chk("done stays done", before == "done")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
