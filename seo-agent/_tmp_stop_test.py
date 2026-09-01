"""Deterministic test: user stop mid-run → clean shutdown.

Fake run_agent flips the session's stop flag and invokes stop_check,
which must raise StopRequested; orchestrator must close the run as
'stopped', emit tool_end + status, and finish with 'done'.
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_tmp = tempfile.mkdtemp(prefix="seo-stop-test-")
os.environ["MEMORY_DIR"] = _tmp
os.environ["SESSIONS_DIR"] = _tmp
os.environ["CACHE_DIR"] = _tmp

from unittest.mock import patch  # noqa: E402

from src import orchestrator, runs  # noqa: E402

routing_resp = {
    "content": "",
    "tool_calls": [
        {"id": "call_1", "name": "seo_agent", "arguments": '{"task": "stop test", "context": ""}'}
    ],
}


def fake_run_agent(message, *, stop_check=None, **kwargs):
    # Simulate the user pressing Stop while the agent runs
    for key in orchestrator._stop_flags:
        orchestrator._stop_flags[key] = True
    if stop_check is not None:
        stop_check()  # must raise StopRequested
    raise AssertionError("FAIL: stop_check did not raise StopRequested")


events = []

def _fake_chat_stream(*a, **k):
    """The streaming shape llm.chat_stream yields: text deltas, then a final
    frame carrying the tool calls."""
    yield {"type": "final", "content": routing_resp["content"],
           "tool_calls": routing_resp["tool_calls"]}

with patch.object(orchestrator.llm, "chat_stream", _fake_chat_stream), \
     patch.object(orchestrator, "run_agent", fake_run_agent):
    gen = orchestrator.run_orchestrator_stream("stop test", None)
    for ev in gen:
        events.append(ev)

types = [e.get("type") for e in events]
print("event types:", types)

tool_ends = [e for e in events if e.get("type") == "tool_end"]
assert tool_ends and tool_ends[0]["success"] is False, "FAIL: no failed tool_end"
statuses = [e.get("content") for e in events if e.get("type") == "status"]
assert "Stopped" in statuses, f"FAIL: no Stopped status, got {statuses}"
assert types[-1] == "done", f"FAIL: stream ended on {types[-1]}"

# Flag must be cleaned up afterwards
assert orchestrator._stop_flags == {}, f"FAIL: flags leaked: {orchestrator._stop_flags}"

# request_stop for an unknown session returns False
assert orchestrator.request_stop("no-such-session") is False

stored = [r for r in runs.list_runs() if r["id"].startswith("chat-")]
run = runs.get_run(stored[0]["id"])
print("run status:", run["status"])
assert run["status"] == "stopped", f"FAIL: run status {run['status']}"
assert run.get("ended"), "FAIL: no ended timestamp"

print("\nPASS: stop mid-run handled cleanly")
