"""Competitor keywords get difficulty from ONE bulk call, and the universe
stays about the business: competitor rows never out-number seed-derived ones."""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.tools import pull_universe as pu  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


calls = []


def fake_bulk(keywords, location_code=2840, language_code="en"):
    calls.append(list(keywords))
    return {k.lower(): 33 for k in keywords if k != "no data"}


rows = [
    {"keyword": "ai product manager", "difficulty": None, "source": "competitor"},
    {"keyword": "Product Strategy", "difficulty": 0, "source": "competitor"},
    {"keyword": "already has kd", "difficulty": 40, "source": "competitor"},
    {"keyword": "no data", "difficulty": None, "source": "competitor"},
]
with patch.object(pu.dfs, "bulk_keyword_difficulty", fake_bulk), patch.object(pu.dfs, "budget_remaining", lambda: 5):
    pu._backfill_difficulty(rows, 2840, "en")
ok(len(calls) == 1, "exactly one call for all missing rows")
ok(sorted(calls[0]) == ["Product Strategy", "ai product manager", "no data"], "only the rows missing KD are sent")
ok(rows[0]["difficulty"] == 33 and rows[1]["difficulty"] == 33, "KD filled, case-insensitively")
ok(rows[2]["difficulty"] == 40, "an existing KD is not overwritten")
ok(rows[3]["difficulty"] is None, "a keyword the endpoint has no data for stays empty, not invented")

calls.clear()
with patch.object(pu.dfs, "bulk_keyword_difficulty", fake_bulk), patch.object(pu.dfs, "budget_remaining", lambda: 0):
    pu._backfill_difficulty([{"keyword": "x", "difficulty": None}], 2840, "en")
ok(calls == [], "no call when the budget is exhausted")

# ---- balance through pull_universe
seed_rows = [{"keyword": f"seed {i}", "volume": 10 + i} for i in range(30)]
comp_rows = [{"keyword": f"comp {i}", "volume": 1000 + i, "source": "competitor", "consensus": (2 if i < 5 else None)}
             for i in range(150)]
with patch.object(pu, "_expand_seed", lambda *a, **k: seed_rows), \
     patch.object(pu, "_seeds_as_keywords", lambda s: []), \
     patch.object(pu, "_competitor_universe", lambda *a, **k: {"queried": ["c.com"], "_rows": comp_rows}), \
     patch.object(pu, "_backfill_difficulty", lambda *a, **k: None), \
     patch.object(pu.dfs, "budget_remaining", lambda: 9):
    out = pu.pull_universe({"business_seeds": ["a"]}, 2840, "en", competitor_urls=["c.com"], site_url="")
kws = out["keywords"]
comp = [k for k in kws if k.get("source") == "competitor"]
seed = [k for k in kws if k.get("source") != "competitor"]
ok(len(seed) == 30, "every seed-derived keyword is kept")
ok(len(comp) == 30, f"competitor rows capped at the seed count, got {len(comp)}")
ok(all(c["consensus"] == 2 for c in comp[:0] or [k for k in comp if k["keyword"] in {f"comp {i}" for i in range(5)}]),
   "consensus keywords are among those kept")
ok(sum(1 for c in comp if c.get("consensus") == 2) == 5, "all five consensus keywords survived the cut")
ok(out["competitors"]["kept_in_universe"] == 30 and out["competitors"]["seed_derived_in_universe"] == 30,
   "the map records the balance")

print(f"backfill/balance: {PASS} assertions passed")
