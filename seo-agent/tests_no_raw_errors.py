"""Internal error text never reaches the model, and so never reaches a bubble.

Observed: a node raised "Could not parse JSON from LLM output", the loop
handed that string to the model as the tool result, the model repeated it
in its reply, and the reply became the artefact's summary. The model must
get a sentence a person can act on; the raw text goes to the server log."""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src import errors  # noqa: E402
from src.tools import strategy_pipeline as sp  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


print("1. errors.user_message hides internals")
for raw in ("Could not parse JSON from LLM output: ", "Error code: 400 - {'error': ...}", "KeyError: 'items'",
            "Traceback (most recent call last): ..."):
    msg = errors.user_message(raw)
    ok("JSON" not in msg and "Traceback" not in msg and "KeyError" not in msg and "400" not in msg,
       f"no internals in the message for {raw[:30]!r}: {msg!r}")

print("2. the graph reports a stopped step, not an exception")
def boom(*a, **k):
    raise ValueError("Could not parse JSON from LLM output: ")
class Rec:
    def __getattr__(self, n): return lambda *a, **k: None
    def active_run_id(self): return "t"
    def market_label(self, *a): return "US-EN"
with patch.object(sp, "_cluster_with_retry", boom),      patch.object(sp, "extract_seeds", lambda *a, **k: {"business_seeds": ["a"], "site_seeds": [], "competitor_seeds": []}),      patch.object(sp, "pull_universe", lambda *a, **k: {"keywords": [{"keyword": "a", "volume": 10}] * 20, "total_count": 20, "competitors": {}}),      patch.object(sp, "rec", Rec()),      patch.object(sp.runs_store, "get_run", lambda *a: {"id": "t", "prompt": "a business"}),      patch.object(sp.market_mod, "require_market", lambda *a, **k: {"location_code": 2840, "language_code": "en", "label": "US-EN"}),      patch.object(sp.site_fetch, "fetch_page", lambda u: {"ok": False, "error": "skipped"}):
    res = sp.run_keyword_strategy("a business", location_code=2840, language_code="en")
ok(res.get("success") is False, "the graph reports failure rather than raising")
ok("JSON" not in str(res.get("error", "")) and "Could not parse" not in str(res.get("error", "")),
   f"the error handed on has no internal text: {res.get('error')!r}")
ok(res.get("stopped_at") == "grouping keywords into themes", f"it names the step it stopped at: {res.get('stopped_at')!r}")
ok(res.get("retry_is_safe") is True, "and says a retry is safe")

print(f"no-raw-errors: {PASS} assertions passed")
