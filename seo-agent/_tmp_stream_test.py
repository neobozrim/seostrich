"""Deterministic test: live stage streaming from the worker thread.

Fake run_agent (running in the worker thread) records stages with pauses
between them. The stream must surface stage events BEFORE tool_end/done,
and the active run id must be visible inside the worker (contextvar
propagation — needed for tool recording and DFS budget keying).
"""
import io
import os
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_tmp = tempfile.mkdtemp(prefix="seo-stream-test-")
os.environ["MEMORY_DIR"] = _tmp
os.environ["SESSIONS_DIR"] = _tmp
os.environ["CACHE_DIR"] = _tmp

from unittest.mock import patch  # noqa: E402

from src import orchestrator, pipeline_recorder, runs  # noqa: E402

routing_resp = {
    "content": "",
    "tool_calls": [
        {"id": "call_1", "name": "seo_agent", "arguments": '{"task": "stream test", "context": ""}'}
    ],
}

seen_in_worker = {}


def fake_run_agent(message, *, stop_check=None, **kwargs):
    # Runs inside ctx.run in the worker thread — the active run id must be set
    seen_in_worker["run_id"] = pipeline_recorder.active_run_id()

    pipeline_recorder.record_tool(
        "extract_seeds", {"source": "test"}, {"seeds": ["ai seo tools"]}, True
    )
    time.sleep(0.7)
    pipeline_recorder.record_tool(
        "keyword_suggestions",
        {"keywords": [{"keyword": "ai seo tools", "volume": 1000, "difficulty": 30, "intent": "commercial"}]},
        [{"keyword": "ai seo tools", "volume": 1000, "difficulty": 30, "intent": "commercial"}],
        True,
    )
    time.sleep(0.7)
    return {
        "messages": [{"role": "assistant", "content": "done"}],
        "session_id": "agent-sess",
        "tool_results": [1, 2],
    }


events = []

def _fake_chat_stream(*a, **k):
    """The streaming shape llm.chat_stream yields: text deltas, then a final
    frame carrying the tool calls."""
    yield {"type": "final", "content": routing_resp["content"],
           "tool_calls": routing_resp["tool_calls"]}

with patch.object(orchestrator.llm, "chat_stream", _fake_chat_stream), \
     patch.object(orchestrator, "run_agent", fake_run_agent):
    gen = orchestrator.run_orchestrator_stream("stream test", None)
    for ev in gen:
        events.append(ev)

types = [e.get("type") for e in events]
print("event types:", types)

# Contextvar reached the worker thread
assert seen_in_worker.get("run_id"), f"FAIL: no active run id in worker, got {seen_in_worker}"

stages = [e for e in events if e.get("type") == "stage"]
stage_ids = [s["stage_id"] for s in stages]
print("stages streamed:", stage_ids)
assert stage_ids == ["seeds", "keywords"], f"FAIL: stage order/ids {stage_ids}"

# Stage events must arrive before the seo_agent tool_end (live, not batched at the end)
first_stage = types.index("stage")
tool_end = types.index("tool_end")
assert first_stage < tool_end, "FAIL: stages not streamed before tool_end"
assert types[-1] == "done", f"FAIL: stream ended on {types[-1]}"

run_id = seen_in_worker["run_id"]
run = runs.get_run(run_id)
assert run["status"] == "done" and run.get("ended"), f"FAIL: run state {run.get('status')}"
assert {s["id"] for s in run["stages"]} == {"seeds", "keywords"}

print("\nPASS: stages stream live from the worker; run id visible in worker context")
