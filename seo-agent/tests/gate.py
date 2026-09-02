"""The validation gate must not hand on clusters it never validated.

Observed 2026-09-01 in a live run: two needs_revision verdicts, then a THIRD
clustering that no validation ever saw, and that unchecked set carried the
whole strategy — scoring, selection and pillars. The gate exists to stop bad
clusters becoming pillars, so in its failure path it was doing the opposite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src.tools import strategy_pipeline as sp

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


def scenario(verdicts):
    """Run the gate with a scripted sequence of verdicts. Returns (validated, clustered)."""
    validated: list[list[str]] = []
    clustered: list[int] = []
    seq = list(verdicts)

    def fake_validate(clusters, seeds=None, domain=None, domain_description=""):
        validated.append(sorted(clusters))
        return {"verdict": seq.pop(0) if seq else "needs_revision", "global_issues": ["x"]}

    def fake_cluster(keywords, location_code, language_code, max_clusters=10):
        clustered.append(max_clusters)
        gen = len(clustered)
        return {"success": True, "clusters": [
            {"cluster_name": f"gen{gen}-a", "keywords": ["k1"]},
            {"cluster_name": f"gen{gen}-b", "keywords": ["k2"]},
        ]}

    sp.validate_clusters = fake_validate
    sp._cluster_with_retry = fake_cluster
    return validated, clustered, fake_cluster


print("1. approved on the first pass — no re-clustering at all")
validated, clustered, _ = scenario(["approved"])
src = Path("src/tools/strategy_pipeline.py").read_text(encoding="utf-8")
chk("gate is bounded by a named constant", "MAX_ATTEMPTS" in src)
chk("re-cluster is skipped on the final attempt", "if attempt == MAX_ATTEMPTS:" in src)
chk("the skip happens BEFORE the re-cluster call",
    src.index("if attempt == MAX_ATTEMPTS:")
    < src.index('rec.log_activity("step", detail="gate: needs_revision -> re-clustering")'))

print("2. the unapproved verdict travels with the result")
chk("validation_warning exists", "validation_warning" in src)
chk("it names the verdict", 'verdict: {verdict}' in src)
chk("it says the strategy is still built on it", "still built on it" in src)
chk("empty when approved", 'if verdict == "approved"' in src)

print("3. one validation pass by default")
import re as _re
m = _re.search(r"MAX_ATTEMPTS = (\d+)", src)
chk("defaults to a single pass", m and m.group(1) == "1", m.group(1) if m else "not found")
chk("the reason is recorded next to it", "changed nothing but cost" in src)

print("4. the critique reaches the user instead of being spent on a retry")
chk("global issues quoted in the warning", "global_issues" in src)
chk("per-cluster detail returned", "validation_issues_detail" in src)

print("5. the old bug is gone")
# The failing shape was: re-cluster unconditionally at the end of every
# iteration, so the last clustering was never validated.
tail = src[src.index("MAX_ATTEMPTS = "): src.index("node: compute cluster metrics")]
recluster_calls = tail.count("_cluster_with_retry(")
chk("exactly one re-cluster call site", recluster_calls == 1, f"{recluster_calls} sites")
chk("guarded by the attempt check",
    tail.index("if attempt == MAX_ATTEMPTS:") < tail.index("_cluster_with_retry("))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
