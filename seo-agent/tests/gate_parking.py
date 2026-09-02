"""The validation gate acts on its own critique.

The validator scores each cluster; a cluster it scores as incoherent is
parked with that reason before selection, never below what selection needs,
and the verdict is re-derived on what remains by the validator's criteria."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
from src.tools.strategy_pipeline import park_incoherent  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


C = [{"name": f"c{i}", "keywords": ["k"]} for i in range(1, 7)]

print("1. the catch-all is parked with the validator's words; the rest pass")
val = {"verdict": "needs_revision", "clusters": [
    {"n": 1, "score": 88, "rec": "keep"}, {"n": 2, "score": 32, "rec": "split", "issue": "catch-all of unrelated tools"},
    {"n": 3, "score": 80, "rec": "keep"}, {"n": 4, "score": 79, "rec": "keep"}, {"n": 5, "score": 90, "rec": "keep"}, {"n": 6, "score": 70, "rec": "keep"}]}
surv, parked, verdict = park_incoherent(C, val, max_select=4)
ok([c["name"] for c in surv] == ["c1", "c3", "c4", "c5", "c6"], f"survivors: {[c['name'] for c in surv]}")
ok(parked[0]["cluster_name"] == "c2" and "32/100" in parked[0]["reason"] and "catch-all" in parked[0]["reason"], f"parked with reason: {parked}")
ok(verdict == "approved", f"verdict on the rest is approved (mean 81.4, min 70): {verdict}")

print("2. 'drop' parks even at a passing score; a low mean stays unapproved")
val2 = {"verdict": "needs_revision", "clusters": [
    {"n": 1, "score": 65, "rec": "drop", "issue": "navigational"}, {"n": 2, "score": 62}, {"n": 3, "score": 61}, {"n": 4, "score": 64}, {"n": 5, "score": 63}, {"n": 6, "score": 66}]}
surv, parked, verdict = park_incoherent(C, val2, max_select=4)
ok([p["cluster_name"] for p in parked] == ["c1"], f"drop is honoured: {parked}")
ok(verdict == "needs_revision", f"mean 63 < 75 keeps the raw verdict: {verdict}")

print("3. never park below what selection needs")
val3 = {"verdict": "rejected", "clusters": [{"n": i, "score": 20} for i in range(1, 7)]}
surv, parked, verdict = park_incoherent(C, val3, max_select=4)
ok(len(surv) == 4 and len(parked) == 2, f"four survivors kept for selection: {len(surv)} / {len(parked)}")
ok(verdict == "rejected", "and the verdict stays rejected")

print("4. nothing to act on -> nothing changes")
surv, parked, verdict = park_incoherent(C, {"verdict": "approved", "clusters": []}, 4)
ok(len(surv) == 6 and not parked and verdict == "approved", "untouched")
surv, parked, verdict = park_incoherent(C, {"verdict": "error"}, 4)
ok(len(surv) == 6 and verdict == "error", "a failed validation parks nothing")

print(f"gate-parking: {PASS} assertions passed")
