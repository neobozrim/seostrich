"""Shape the real productpirates pipeline output into a structured run artifact.

Reads pp_final_results.json + intake-productpirates.yaml and writes
seed/runs/productpirates.json — the default/example run the UI renders.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

BASE = Path(__file__).parent


def load_pp():
    return json.loads((BASE / "pp_final_results.json").read_text(encoding="utf-8"))


def load_intake():
    return yaml.safe_load(
        (BASE / "intake-productpirates.yaml").read_text(encoding="utf-8")
    )


def build_clusters(pp):
    """Merge revised keyword lists with scored metadata into one cluster list."""
    scored = {
        c.get("cluster_name"): c for c in pp.get("scored", {}).get("scored_clusters", [])
    }
    revised = pp.get("clusters_revised", {})
    clusters = []
    # Preserve the order used in the scored output
    for name in [c.get("cluster_name") for c in pp.get("scored", {}).get("scored_clusters", [])]:
        meta = scored.get(name, {})
        clusters.append(
            {
                "name": name,
                "seo_score": meta.get("seo_score"),
                "geo_score": meta.get("geo_score"),
                "combined_score": meta.get("combined_score"),
                "rationale": meta.get("seo_rationale", ""),
                "keywords": revised.get(name, []),
            }
        )
    return clusters


def build_run():
    pp = load_pp()
    intake = load_intake()
    seeds = pp.get("seeds", {})
    universe = pp.get("universe", {}).get("keywords", [])
    clusters = build_clusters(pp)
    pillars = pp.get("pillars", {}).get("pillars", [])
    calendar = pp.get("calendar", {}).get("calendar", [])

    stages = [
        {
            "id": "intake",
            "label": "Intake",
            "status": "done",
            "artifact": {
                "domain": intake.get("domain"),
                "description": (intake.get("description") or "").strip(),
                "goal": (intake.get("goal") or "").strip(),
                "locale": intake.get("locale", {}),
                "competitors": intake.get("competitors", []),
                "optimization_mix": intake.get("optimization_mix"),
                "notes": (intake.get("notes") or "").strip(),
            },
        },
        {
            "id": "seeds",
            "label": "Seed phrases",
            "status": "done",
            "artifact": {
                "business_seeds": seeds.get("business_seeds", []),
                "site_seeds": seeds.get("site_seeds", []),
                "competitor_seeds": seeds.get("competitor_seeds", []),
            },
        },
        {
            "id": "keywords",
            "label": "Keyword universe",
            "status": "done",
            "artifact": {
                "count": len(universe),
                "keywords": universe,
            },
        },
        {
            "id": "clusters",
            "label": "Keyword clusters",
            "status": "done",
            "artifact": {
                "count": len(clusters),
                "clusters": clusters,
            },
        },
        {
            "id": "pillars",
            "label": "Content pillars",
            "status": "done",
            "artifact": {
                "count": len(pillars),
                "pillars": pillars,
            },
        },
        {
            "id": "mix",
            "label": "Content calendar",
            "status": "done",
            "artifact": {
                "count": len(calendar),
                "calendar": calendar,
                "serp_analysis": pp.get("serp_analysis", {}),
                "competitor_overlap": pp.get("competitor_overlap", {}),
            },
        },
    ]

    return {
        "id": "productpirates",
        "project": intake.get("domain"),
        "title": "Product Pirates Club",
        "created": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "stages": stages,
        "feedback": [],
    }


def main():
    run = build_run()
    out_dir = BASE / "seed" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "productpirates.json"
    out_path.write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # sanity check
    stage_sizes = {s["id"]: len(json.dumps(s["artifact"])) for s in run["stages"]}
    print("Wrote", out_path)
    print("Total bytes:", out_path.stat().st_size)
    print("Stage artifact sizes:", stage_sizes)
    print("Keywords:", run["stages"][2]["artifact"]["count"])
    print("Clusters:", run["stages"][3]["artifact"]["count"])
    print("Pillars:", run["stages"][4]["artifact"]["count"])
    print("Calendar:", run["stages"][5]["artifact"]["count"])


if __name__ == "__main__":
    main()
