import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
from src import market, pipeline_recorder as rec
from src.tools.strategy_pipeline import run_keyword_strategy

ok = fail = 0
def check(label, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS {label}")
    else: fail += 1; print(f"  FAIL {label} {extra}")

RUN = "test-market-run"
rec.begin_run(RUN, "market gate test")
market.reset(RUN)

print("1. graph refuses without a confirmed market")
r = run_keyword_strategy("Spoken-word poetry performances", site_description="izrechena.com")
check("refused", r.get("success") is False and r.get("needs") == "confirm_market")
check("error names confirm_market", "confirm_market" in r.get("error", ""))
check("error forbids inferring", "never infer" in r.get("error", "").lower()
      or "TLD" in r.get("error", ""), r.get("error", "")[:120])

print("2. graph refuses even when the LLM passes a guessed market")
r = run_keyword_strategy("Spoken-word poetry", location_code=2100, language_code="bg")
check("guessed BG still refused", r.get("success") is False and r.get("needs") == "confirm_market")

print("3. bad inputs are rejected with usable choices")
check("unknown country", market.resolve("Wakanda", "en").get("ok") is False)
check("offers catalog", len(market.resolve("Wakanda", "en").get("available_markets", [])) > 5)
r = market.resolve("BG", "")
check("missing language refused", r.get("ok") is False)
check("suggests languages", "bg" in r.get("suggested_languages", []))

print("4. confirmation pins the market to the run")
c = market.confirm_market("Bulgaria", "bg", run_id=RUN)
check("confirmed", c.get("ok") and c["location_code"] == 2100 and c["language_code"] == "bg", str(c)[:140])
check("label", c.get("label") == "BG-BG")
check("readback", (market.confirmed_market(RUN) or {}).get("label") == "BG-BG")

print("5. a pinned run cannot be silently re-targeted")
try:
    market.require_market(location_code=2840, language_code="en", run_id=RUN)
    check("mismatch raises", False, "did not raise")
except market.MarketNotConfirmed as e:
    check("mismatch raises", True)
    check("message says ask the user", "ask the user" in str(e).lower())
check("matching code accepted", market.require_market(2100, "bg", run_id=RUN)["label"] == "BG-BG")
check("no args -> pinned market", market.require_market(run_id=RUN)["label"] == "BG-BG")

print("6. the real bug: a .bg domain targeting English buyers")
market.reset(RUN)
c = market.confirm_market("US", "en", run_id=RUN)
check("bg domain can target US-EN", c["location_code"] == 2840 and c["language_code"] == "en")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
