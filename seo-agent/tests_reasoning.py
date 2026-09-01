"""Every cluster decision must carry its reasoning, on both sides of the cut.

The pipeline explained why it dropped a cluster but not why it kept one, and
the explanations that did exist were scattered across five differently-named
fields among ~19 keys — so a calling agent had to know the schema to find them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import cluster_governance as gov
from src import pipeline_recorder as rec
from src import runs

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RID = "test-reasoning-run"
runs.save_run(RID, {
    "id": RID, "project": "T", "title": "reasoning", "status": "done",
    "stages": [{"id": "clusters", "label": "Clusters", "status": "done", "artifact": {
        "count": 3,
        "clusters": [
            {"name": "KG Tutorials", "cluster_name": "KG Tutorials", "head_term": "knowledge graph tutorial",
             "keywords": ["knowledge graph tutorial"], "rationale": "all about building KGs",
             "seo_score": 40, "geo_score": 90, "combined_score": 65, "opportunity": "high",
             "seo_rationale": "low volume", "geo_rationale": "highly citable"},
            {"name": "PM Tools", "cluster_name": "PM Tools", "head_term": "ai product management tools",
             "keywords": ["ai product management tools"], "rationale": "tool queries"},
            {"name": "PM Certs", "cluster_name": "PM Certs", "head_term": "ai pm certification",
             "keywords": ["ai pm certification"], "rationale": "certification queries"},
        ],
    }}],
})

print("1. the recorder attaches a reason to BOTH sides")
rec._apply_selection(runs.get_run(RID), {"selection": {
    "selected": ["KG Tutorials"],
    "selected_reasons": [{"cluster_name": "KG Tutorials",
                          "reason": "Owns the technical depth angle this community is built on."}],
    "discarded": [{"cluster_name": "PM Tools", "reason": "Off-topic: generic tool queries."},
                  {"cluster_name": "PM Certs", "reason": "Off-topic: certification seekers, not builders."}],
}})
run = runs.get_run(RID)
# _apply_selection mutates the dict it is given, so re-apply on the stored run
run_obj = runs.get_run(RID)
rec._apply_selection(run_obj, {"selection": {
    "selected": ["KG Tutorials"],
    "selected_reasons": [{"cluster_name": "KG Tutorials",
                          "reason": "Owns the technical depth angle this community is built on."}],
    "discarded": [{"cluster_name": "PM Tools", "reason": "Off-topic: generic tool queries."},
                  {"cluster_name": "PM Certs", "reason": "Off-topic: certification seekers, not builders."}],
}})
runs.save_run(RID, run_obj)

data = gov.list_clusters_all(RID)
chk("selection recorded", data["selection_made"] is True)
chk("1 selected, 2 discarded",
    len(data["selected"]) == 1 and len(data["discarded"]) == 2,
    f"{len(data['selected'])}/{len(data['discarded'])}")

print("2. selected clusters explain themselves")
sel = data["selected"][0]
chk("has a reasoning block", "reasoning" in sel)
chk("decision is labelled", sel["reasoning"]["decision"] == "selected")
chk("decision_reason is populated", "technical depth" in sel["reasoning"]["decision_reason"],
    sel["reasoning"]["decision_reason"])
chk("keeps why the keywords group", sel["reasoning"]["why_these_keywords_group"] == "all about building KGs")
chk("carries the score rationales",
    sel["reasoning"]["seo_rationale"] == "low volume"
    and sel["reasoning"]["geo_rationale"] == "highly citable")
chk("measured metrics exposed", isinstance(sel["reasoning"]["metrics"], dict))
chk("opportunity label present", "opportunity" in sel["reasoning"])
# The fixture carries the old model-estimated scores; they must be surfaced
# separately and labelled, never mixed in with the measurements.
chk("legacy model scores quarantined", "legacy_model_scores" in sel["reasoning"])
chk("legacy block is labelled as estimated",
    "Estimated by a model" in sel["reasoning"]["legacy_model_scores"]["note"])
chk("legacy values preserved", sel["reasoning"]["legacy_model_scores"]["combined"] == 65)

print("3. discarded clusters keep theirs")
for d in data["discarded"]:
    chk(f"{d['cluster_name']:<12} decision labelled", d["reasoning"]["decision"] == "discarded")
    chk(f"{d['cluster_name']:<12} has a real reason",
        "Off-topic" in d["reasoning"]["decision_reason"], d["reasoning"]["decision_reason"])

print("4. the shape is stable, not raw internals")
for entry in data["selected"] + data["discarded"]:
    chk(f"{entry['cluster_name']:<12} has the stable keys",
        {"cluster_name", "head_term", "keyword_count", "keywords", "reasoning"} <= set(entry))
    chk(f"{entry['cluster_name']:<12} keywords normalised to dicts",
        all(isinstance(k, dict) for k in entry["keywords"]))
chk("caller is told what the reasoning block means", "decision_reason" in data["note"])

print("5. promoting back leaves a reason, not a blank")
gov.promote_cluster(RID, "PM Tools")
after = gov.list_clusters_all(RID)
promoted = next(c for c in after["selected"] if c["cluster_name"] == "PM Tools")
chk("promoted cluster is now selected", promoted["reasoning"]["decision"] == "selected")
chk("and says why it is there", bool(promoted["reasoning"]["decision_reason"]),
    promoted["reasoning"]["decision_reason"])

print("6. discarding records the user's reason")
gov.discard_cluster(RID, "PM Tools", "Tried it, still not our audience.")
after = gov.list_clusters_all(RID)
dropped = next(c for c in after["discarded"] if c["cluster_name"] == "PM Tools")
chk("user reason preserved", "still not our audience" in dropped["reasoning"]["decision_reason"],
    dropped["reasoning"]["decision_reason"])

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
