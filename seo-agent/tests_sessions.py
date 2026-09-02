"""Chat history: sessions are listed with a title, loaded as plain messages,
and session ids are validated before they become file names."""
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tmp = Path(tempfile.mkdtemp(prefix="seo-sessions-"))
os.environ["SESSIONS_DIR"] = str(tmp)
for v in ("APP_USERNAME", "APP_PASSWORD", "PASSWORD", "USERNAME", "USER_NAME", "APP_USER", "APP_PASS"):
    os.environ[v] = ""

from src import session as ss  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


print("1. ids are validated")
for bad in ["../x", "..", "a/b", "", "a\\b", "x;y"]:
    ok(ss.load_session(bad) is None, f"load rejects {bad!r}")
    try:
        ss.save_session(bad, {"messages": []})
        ok(False, f"save rejected {bad!r}")
    except ValueError:
        ok(True, f"save rejects {bad!r}")

print("2. summary and messages")
sid = ss.new_session_id()
ss.save_session(sid, {"session_id": sid, "messages": [
    {"role": "user", "content": "  Build a content strategy for   Unblocked blog — practitioner-level, code-adjacent " + "x" * 200},
    {"role": "assistant", "content": "Sure."},
    {"role": "tool", "content": "{...}"},
    {"role": "assistant", "content": ""},
], "agent_calls": [1, 2]})
summary = ss.session_summary(sid)
ok(summary["id"] == sid, "summary carries the id")
ok(summary["title"].startswith("Build a content strategy for Unblocked blog"), "title is the first user message, whitespace collapsed")
ok(len(summary["title"]) <= 90, "title is capped")
ok(summary["messages"] == 3, "counts user+assistant messages only")
ok(ss.session_summary("does-not-exist") is None, "missing session -> None")

print("3. the API")
from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402
c = TestClient(app)
r = c.get("/api/sessions")
ok(r.status_code == 200, "list ok")
ids = [x["id"] for x in r.json()]
ok(sid in ids, "the session is listed")
ok(all("title" in x for x in r.json()), "every entry has a title")

empty = ss.new_session_id()
ss.save_session(empty, {"session_id": empty, "messages": [], "agent_calls": []})
ok(empty not in [x["id"] for x in c.get("/api/sessions").json()], "an empty session is not listed")

r = c.get(f"/api/sessions/{sid}")
ok(r.status_code == 200, "session fetch ok")
msgs = r.json()["messages"]
ok([m["role"] for m in msgs] == ["user", "assistant"], "only user/assistant with content are returned")
ok(c.get("/api/sessions/nope").status_code == 404, "unknown -> 404")
ok(c.get("/api/sessions/..%2F..%2Fx").status_code in (404, 422), "traversal -> not found")

print(f"sessions: {PASS} assertions passed")
