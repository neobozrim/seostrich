"""When the relevance gate fails, the pipeline must say so — not fake a decision.

Observed 2026-09-01: select_clusters failed, and the fallback took the first N
clusters in emission order and labelled the rest "not selected (deterministic
fallback)". It kept three near-duplicate course-buying clusters and discarded
"Building AI Products", "Agentic AI Development" and "AI Product Evaluation" —
the subject the business is actually about. Nothing in the output said a
relevance judgement had never been made.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SRC = Path("src/tools/strategy_pipeline.py").read_text(encoding="utf-8")
AGENT = Path("src/agent.py").read_text(encoding="utf-8")

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


print("1. a transient failure gets a retry before any fallback")
gate = SRC[SRC.index("selection_res = select_clusters("):SRC.index('steps.append("selection")')]
chk("select_clusters called twice", gate.count("select_clusters(") == 2, str(gate.count("select_clusters(")))
chk("the retry is logged", "retrying once" in gate)

print("2. the fallback no longer pretends to be a decision")
chk("the old misleading label is gone",
    "not selected (deterministic fallback)" not in SRC)
# Strip comments before asserting on behaviour: the old slice is quoted in a
# comment explaining the bug, and a naive substring check matches that prose.
CODE = chr(10).join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
chk("no longer takes emission order", "names[:max_select]" not in CODE)
chk("but the reason is still documented", "names[:max_select]" in SRC)
chk("ranks by measured volume instead", "total_volume" in gate)
chk("kept clusters say relevance was not checked",
    "no one checked whether this serves your" in gate)
chk("dropped clusters say they were NOT judged off-topic",
    "NOT judged off-topic" in gate)
chk("and invite promotion", "promote it if so" in gate)

print("3. the failure travels out of the pipeline")
chk("relevance_gate_ran returned", "relevance_gate_ran" in SRC)
chk("selection_warning returned", "selection_warning" in SRC)
chk("warning names the cause", "selection_error" in SRC)
chk("warning survives the compact projection",
    '"selection_warning": result.get("selection_warning")' in SRC)
chk("relevance_gate_ran survives it too",
    '"relevance_gate_ran": result.get("relevance_gate_ran")' in SRC)

print("4. the agent is required to report it")
chk("prompt covers the skipped gate", "relevance gate did not run" in AGENT.lower())
chk("prompt says lead with it", "Lead with it" in AGENT)
chk("prompt forbids passing it off as a strategy",
    "Do not present a volume-only selection as a strategy" in AGENT)

print("5. the deliverable is reachable, not summarised away")
# The first attempt at the truncation problem was a projection that picked
# "the important fields". That hides whatever the chooser did not think of,
# at the step where the agent is doing the judging — so the full result is
# persisted and the agent reads what it needs.
chk("no opinionated projection", "_compact_result" not in SRC)
chk("the manifest comes from the stages", "stage_manifest(" in SRC)
chk("a manifest is returned", '"recorded_stages": manifest' in SRC)
chk("the agent is told how to read it", "read_run_section" in SRC)
chk("warnings still ride inline, not buried in a file",
    '"selection_warning": result.get("selection_warning")' in SRC)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
