"""Deterministic test: orchestrator must survive a run_agent crash.

Mocks LLM (routing to seo_agent) and forces run_agent to raise the
production error class; asserts run store gets status=error, and the
stream emits tool_end(success=False) + error + done without dying.
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_tmp = tempfile.mkdtemp(prefix="seo-crash-test-")
os.environ["MEMORY_DIR"] = _tmp
os.environ["SESSIONS_DIR"] = _tmp
os.environ["CACHE_DIR"] = _tmp
os.environ["MOCK_LLM"] = "1"

from unittest.mock import patch  # noqa: E402

from src import orchestrator, runs  # noqa: E402

PROD_ERROR = ValueError("Expecting ',' delimiter: line 1 column 3864 (char 3863)")

routing_resp = {
    "content": "",
    "tool_calls": [
        {"id": "call_1", "name": "seo_agent", "arguments": '{"task": "test task", "context": ""}'}
    ],
}

events = []

def _fake_chat_stream(*a, **k):
    """The streaming shape llm.chat_stream yields: text deltas, then a final
    frame carrying the tool calls."""
    yield {"type": "final", "content": routing_resp["content"],
           "tool_calls": routing_resp["tool_calls"]}

with patch.object(orchestrator.llm, "chat_stream", _fake_chat_stream), \
     patch.object(orchestrator, "run_agent", side_effect=PROD_ERROR):
    gen = orchestrator.run_orchestrator_stream("crash test", None)
    for ev in gen:
        events.append(ev)

types = [e.get("type") for e in events]
print("event types:", types)

tool_ends = [e for e in events if e.get("type") == "tool_end"]
errors = [e for e in events if e.get("type") == "error"]
assert tool_ends, "FAIL: no tool_end emitted (spinner would hang)"
assert tool_ends[0]["success"] is False, "FAIL: tool_end should be success=False"
assert errors, "FAIL: no error event emitted"
assert types[-1] == "done", f"FAIL: stream did not reach done, last={types[-1]}"

stored = runs.list_runs()
chat_runs = [r for r in stored if r["id"].startswith("chat-")]
assert chat_runs, "FAIL: no chat run recorded"
run = runs.get_run(chat_runs[0]["id"])
print("run status :", run["status"])
print("run error  :", run.get("error"))
print("run ended  :", run.get("ended"))
assert run["status"] == "error", f"FAIL: run stuck status={run['status']}"
assert "Expecting" in run.get("error", ""), "FAIL: error not stored on run"
assert run.get("ended"), "FAIL: no ended timestamp"

print("\nPASS: crash contained — run closed as error, stream completed cleanly")
