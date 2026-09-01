"""The agent reads its own run; nothing is summarised away.

Tool results cap at 4,000 chars and these graphs return far more. The first fix
was a projection that chose "the important fields" — which puts one person's
guess between the agent and its own work, and drops whatever they did not think
of, at the step where judgement matters most. Now the full result is persisted
and the agent pages through whatever it decides it needs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import pipeline_recorder as rec
from src import runs as runs_store
from src.tools.run_sections import PAGE, read_run_section, write_full_result

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RID = "test-sections-run"
runs_store.save_run(RID, {"id": RID, "project": "t", "title": "t", "status": "done", "stages": []})

BIG = {
    "brief": [{"topic": f"topic {i}", "questions": [f"q{i}-{j}" for j in range(40)]} for i in range(6)],
    "ranked": [{"topic": f"topic {i}", "volume": i * 100} for i in range(6)],
    "cost_note": "one cheap call, six paid calls",
}

print("1. the whole result is persisted, not trimmed")
manifest = write_full_result(RID, "geo_demand", BIG)
full = len(json.dumps(BIG, ensure_ascii=False, indent=2, default=str))
chk("manifest reports the true size", manifest["total_chars"] == full, f"{manifest['total_chars']} vs {full}")
chk("it is larger than a tool result could carry", full > 4000, str(full))
chk("every section is listed", {s["section"] for s in manifest["sections"]} == set(BIG))
chk("sizes are given", all(s["chars"] > 0 for s in manifest["sections"]))
chk("page counts are given", all(s["pages"] >= 1 for s in manifest["sections"]))

print("2. the agent can list what exists without guessing")
with rec.use_run(RID):
    listing = read_run_section("geo_demand")
chk("sections listed", {s["section"] for s in listing["sections"]} == set(BIG))
chk("told how to continue", "section=" in listing["hint"])

print("3. long sections page instead of truncating")
with rec.use_run(RID):
    p1 = read_run_section("geo_demand", "brief", page=1)
chk("page 1 returned", p1["page"] == 1)
chk("more pages flagged", p1["more"] is True, str(p1.get("of_pages")))
chk("chunk fits a tool result", len(p1["content"]) <= PAGE, str(len(p1["content"])))
chk("next call is spelled out", "page=2" in p1["next"])

with rec.use_run(RID):
    pages = []
    page = 1
    while True:
        r = read_run_section("geo_demand", "brief", page=page)
        pages.append(r["content"])
        if not r["more"]:
            break
        page += 1
rebuilt = "".join(pages)
original = json.dumps(BIG["brief"], ensure_ascii=False, indent=2, default=str)
chk("paging reconstructs the section EXACTLY", rebuilt == original,
    f"{len(rebuilt)} vs {len(original)}")
chk("no question was lost", rebuilt.count('"q5-39"') == 1)

print("4. mistakes are answerable, not dead ends")
with rec.use_run(RID):
    bad = read_run_section("geo_demand", "nope")
chk("unknown section lists the real ones", set(bad["available"]) == set(BIG), str(bad))
with rec.use_run(RID):
    missing = read_run_section("does_not_exist")
chk("unknown artifact says what exists", "available" in missing, str(missing))
with rec.use_run(RID):
    over = read_run_section("geo_demand", "brief", page=999)
chk("page past the end clamps", over["page"] == over["of_pages"], str(over["page"]))
chk("outside a run it explains itself", "error" in read_run_section("geo_demand"))

print("5. the graphs hand back a manifest, not a chosen subset")
strat = Path("src/tools/strategy_pipeline.py").read_text(encoding="utf-8")
geo = Path("src/tools/geo_demand.py").read_text(encoding="utf-8")
chk("strategy persists everything", "write_full_result(run_id, \"keyword_strategy\"" in strat)
chk("geo persists everything", "write_full_result(run_id, \"geo_demand\"" in geo)
chk("no opinionated projection left in strategy", "_compact_result" not in strat)
chk("no opinionated projection left in geo", "def _compact(" not in geo)
chk("strategy tells the agent how to read", "read_run_section" in strat)
chk("geo tells the agent how to read", "read_run_section" in geo)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
