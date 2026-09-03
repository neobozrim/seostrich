"""Steer stops a graph between nodes, and says so as a stop, not an error.

The stop flag lives with the orchestrator per session; graphs only know
their run. A hook registered per run is consulted at every node boundary.
Before this a steer could only take effect after the whole graph."""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src import pipeline_recorder as rec  # noqa: E402
from src.tools import strategy_pipeline as sp  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


class StopRequested(Exception):
    pass


print("1. no hook, nothing happens")
with rec.use_run("test-steer"):
    rec.check_stop()
ok(True, "check_stop is a no-op without a hook")

print("2. a registered hook raises at the next node boundary")
def raise_stop():
    raise StopRequested()
rec.set_stop_hook("test-steer", raise_stop)
raised = False
with rec.use_run("test-steer"):
    try:
        sp._step("pulling keyword data")
    except StopRequested:
        raised = True
ok(raised, "the strategy graph's node boundary raises the stop")
with rec.use_run("test-other"):
    sp._step("pulling keyword data")
ok(True, "another run is unaffected")

print("3. the graph wrapper reports a user stop as a stop, not a failure")
class Rec:
    def __getattr__(self, n): return lambda *a, **k: None
    def active_run_id(self): return "test-steer"
    def check_stop(self): raise StopRequested()
def stopped_node(*a, **k):
    sp._step("grouping keywords into themes")
with patch.object(sp, "_run_keyword_strategy", stopped_node), patch.object(sp, "rec", Rec()):
    res = sp.run_keyword_strategy("a business", location_code=2840, language_code="en")
ok(res.get("success") is False and res.get("stopped_by_user") is True, f"stopped by user, not an error: {res}")
ok("You stopped the run" in res.get("error", "") and "grouping keywords into themes" in res.get("error", ""), f"the message names the step: {res.get('error')}")

print("4. end_run clears the hook")
rec.end_run("test-steer")
with rec.use_run("test-steer"):
    rec.check_stop()
ok(True, "cleared")

print(f"steer: {PASS} assertions passed")
