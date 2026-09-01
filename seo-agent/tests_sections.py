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
from src.tools.run_sections import PAGE, read_run_section, stage_manifest

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
    "brief": [{"topic": f"topic {i}", "questions": [f"q{i}-{j} what do AI engines answer here" for j in range(40)]} for i in range(6)],
    "ranked": [{"topic": f"topic {i}", "volume": i * 100} for i in range(6)],
    "cost_note": "one cheap call, six paid calls",
}

# The stages ARE the store — no second copy. Record BIG as a stage.
runs_store.save_run(RID, {"id": RID, "project": "t", "title": "t", "status": "done",
    "stages": [{"id": "ai_citability", "label": "AI citability", "status": "done",
                "artifact": BIG}]})

print("1. the whole result is readable from the stage, not trimmed")
manifest = stage_manifest(RID)
full = len(json.dumps(BIG, ensure_ascii=False, default=str))
chk("manifest reports the true size", manifest["stages"][0]["chars"] == full,
    f"{manifest['stages'][0]['chars']} vs {full}")
chk("it is larger than a tool result could carry", full > 4000, str(full))
chk("every section is listed", set(manifest["stages"][0]["sections"]) == set(BIG))
chk("size is given", manifest["stages"][0]["chars"] > 0)
chk("page count is given", manifest["stages"][0]["pages"] >= 1)

print("2. the agent can list what exists without guessing")
with rec.use_run(RID):
    listing = read_run_section("ai_citability")
chk("sections listed", {s["section"] for s in listing["sections"]} == set(BIG))
chk("told how to continue", "section=" in listing["hint"])

print("3. long sections page instead of truncating")
with rec.use_run(RID):
    p1 = read_run_section("ai_citability", "brief", page=1)
chk("page 1 returned", p1["page"] == 1)
chk("more pages flagged", p1["more"] is True, str(p1.get("of_pages")))
chk("chunk fits a tool result", len(p1["content"]) <= PAGE, str(len(p1["content"])))
chk("next call is spelled out", "page=2" in p1["next"])

with rec.use_run(RID):
    pages = []
    page = 1
    while True:
        r = read_run_section("ai_citability", "brief", page=page)
        pages.append(r["content"])
        if not r["more"]:
            break
        page += 1
rebuilt = "".join(pages)
original = json.dumps(BIG["brief"], ensure_ascii=False, indent=2, default=str)
chk("paging reconstructs the section EXACTLY", rebuilt == original,
    f"{len(rebuilt)} vs {len(original)}")
chk("no question was lost", rebuilt.count("q5-39 what do AI engines answer here") == 1)

print("3b. the manifest points at the sections a report actually needs")
m = stage_manifest(RID)
chk("hint tells the agent where to start", "usually_wanted" in m["hint"], m["hint"][:60])
chk("pages are as large as the cap allows", PAGE >= 3500, str(PAGE))

runs_store.save_run("test-wanted", {"id": "test-wanted", "project": "t", "title": "t",
    "status": "done", "stages": [
        {"id": "clusters", "label": "Clusters", "status": "done",
         "artifact": {"clusters": [1], "discarded": [2], "count": 3, "selected": True}},
        {"id": "pillars", "label": "Pillars", "status": "done",
         "artifact": {"pillars": [1], "skipped": []}},
    ]})
wm = stage_manifest("test-wanted")
by = {x["stage"]: x for x in wm["stages"]}
chk("clusters flags clusters + discarded",
    by["clusters"].get("usually_wanted") == ["clusters", "discarded"],
    str(by["clusters"].get("usually_wanted")))
chk("pillars flags pillars", by["pillars"].get("usually_wanted") == ["pillars"])
chk("noise is not flagged", "count" not in (by["clusters"].get("usually_wanted") or []))

print("4. mistakes are answerable, not dead ends")
with rec.use_run(RID):
    bad = read_run_section("ai_citability", "nope")
chk("unknown section lists the real ones", set(bad["available"]) == set(BIG), str(bad))
with rec.use_run(RID):
    missing = read_run_section("does_not_exist_stage")
chk("unknown stage says what exists", "available" in missing, str(missing))
with rec.use_run(RID):
    over = read_run_section("ai_citability", "brief", page=999)
chk("page past the end clamps", over["page"] == over["of_pages"], str(over["page"]))
chk("outside a run it explains itself", "error" in read_run_section("ai_citability"))

print("5. the graphs hand back a manifest, not a chosen subset")
strat = Path("src/tools/strategy_pipeline.py").read_text(encoding="utf-8")
geo = Path("src/tools/geo_demand.py").read_text(encoding="utf-8")
chk("strategy reports the stage manifest", "stage_manifest(" in strat)
chk("geo reports the stage manifest", "stage_manifest(" in geo)
chk("no opinionated projection left in strategy", "_compact_result" not in strat)
chk("no opinionated projection left in geo", "def _compact(" not in geo)
chk("strategy tells the agent how to read", "read_run_section" in strat)
chk("geo tells the agent how to read", "read_run_section" in geo)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
