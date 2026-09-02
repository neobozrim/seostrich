"""Exception text must never reach the chat bubble unfiltered."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src.errors import detail, is_recoverable, user_message

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


# Real failures observed in this project's own run history.
REAL = [
    ("run_keyword_strategy() got an unexpected keyword argument 'angle'", True, "tool"),
    ("Request timed out.", True, "retry"),
    ("DataForSEO call budget reached: 40 calls so far (keyword_suggestions x19) against a cap of 40 per run.", True, "budget"),
    ("No market confirmed for this run. Ask the user which COUNTRY and which LANGUAGE to target", True, "market"),
    ("Error code: 401 - {'error': {'message': 'invalid api key'}}", False, "credential"),
    ("Could not parse JSON from LLM output: {\"clusters\": [", True, "parse"),
    ("HTTPSConnectionPool: Max retries exceeded (Connection refused)", True, "network"),
    ("something nobody predicted", True, "fallback"),
]

print("1. no message leaks internals")
LEAKY = ("Traceback", "()", "Error code:", "__", "0x", "line ", ".py")
for raw, _, kind in REAL:
    msg = user_message(raw)
    chk(f"{kind:<11} message is clean", not any(t in msg for t in LEAKY), msg[:70])
    chk(f"{kind:<11} says something useful", len(msg) > 40 and msg.endswith(("." , "?")), msg[:70])

print("2. recoverability is classified")
for raw, recoverable, kind in REAL:
    chk(f"{kind:<11} recoverable={recoverable}", is_recoverable(raw) is recoverable)

print("3. distinct causes get distinct guidance")
msgs = {user_message(r) for r, _, _ in REAL}
chk("not one generic message for everything", len(msgs) >= 6, f"{len(msgs)} distinct")
chk("budget message mentions continuing", "continue" in user_message(REAL[2][0]).lower())
chk("market message asks for country and language",
    "country" in user_message(REAL[3][0]).lower() and "language" in user_message(REAL[3][0]).lower())

print("4. raw detail is preserved for the run record")
try:
    raise ValueError("boom")
except ValueError as exc:
    chk("detail keeps type and text", detail(exc) == "ValueError: boom", detail(exc))
    chk("detail is bounded", len(detail(RuntimeError("x" * 9999))) <= 500)
chk("empty exception still yields guidance", len(user_message("")) > 40)

print("5. the orchestrator sends the friendly form, not str(exc)")
orch = Path("src/orchestrator.py").read_text(encoding="utf-8")
chk("no raw str(e) in an error event", '"content": str(e)' not in orch)
chk("no raw str(err) in an error event", '"content": str(err)' not in orch)
chk("uses errors.user_message", "errors.user_message" in orch)
chk("still records the detail", "errors.detail" in orch)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
