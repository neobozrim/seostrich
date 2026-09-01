"""Does validate_clusters need the reasoning model?

It is now the dominant cost in the strategy graph — 118.8s + 85.2s across two
attempts on the last live run, 36% of total, and BOTH returned needs_revision,
so the deliberation improved nothing that run. Flash matched max on clustering,
seed extraction and scoring. This asks whether the same holds here, where the
job is a judgement call rather than mechanical work.

A verdict is only useful if it is stable and justified, so compare three things:
the verdict itself, how long it took, and whether the issues it raises are
specific enough to act on.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import llm
from src.config import settings
from src.tools import validate_clusters as vc

# Real clusters from the Product Pirates run, with the shape the node receives.
CLUSTERS = {
    "Career": [
        "ai product manager", "ai product manager jobs", "ai product manager salary",
        "how to become an ai product manager", "ai product manager skills",
        "ai product manager job description",
    ],
    "Course Discovery": [
        "ai product management course", "ai product management courses",
        "best ai product management course", "ai pm course", "ai product manager course",
        "coursera ai product management", "maven ai product management",
        "ai product management training", "ai product management bootcamp",
    ],
    "Certification": [
        "ai product manager certification", "ai product management certificate",
        "ibm ai product manager professional certificate",
        "microsoft ai product manager professional certificate",
        "ai product management specialization",
    ],
    "Agentic Resources": [
        "agentic ai for product managers", "hands on agentic ai projects",
        "build ai products", "how to build ai products", "ai product building",
        "agentic commerce building blocks", "knowledge graph explained",
        "open source llm evaluation", "llm evaluation framework",
        "ai product management newsletter", "ai product management book",
        "ai product community", "ai native product manager",
    ],
    "Providers": [
        "pendo ai for product management", "productboard ai", "amplitude ai",
    ],
    "Selection": [
        "best ai tools for product managers", "ai tools for product management",
    ],
}

SEEDS = {"business_seeds": ["ai product community", "hands-on AI building"],
         "site_seeds": ["knowledge graphs", "open source llm evaluation"]}
BUSINESS = (
    "Product Pirates — an AI community of practice for product people who want "
    "hands-on experience building AI products. Deep dives dissecting real "
    "solutions, not theory or prompt-engineering content."
)

original_chat = llm.chat


def run_with(model: str) -> dict:
    def patched(*args, **kwargs):
        kwargs["model"] = model
        return original_chat(*args, **kwargs)

    vc.llm.chat = patched
    start = time.time()
    try:
        result = vc.validate_clusters(CLUSTERS, seeds=SEEDS, domain_description=BUSINESS)
        return {"model": model, "seconds": time.time() - start, "result": result}
    except Exception as exc:
        return {"model": model, "seconds": time.time() - start,
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        vc.llm.chat = original_chat


print(f"clusters: {len(CLUSTERS)}  keywords: {sum(len(v) for v in CLUSTERS.values())}\n")

for model in (settings.qwen_model, settings.qwen_model_fast):
    out = run_with(model)
    if out.get("error"):
        print(f"  {model:16} {out['seconds']:6.1f}s  ERR {out['error'][:90]}")
        continue
    r = out["result"] or {}
    issues = r.get("global_issues") or []
    per_cluster = r.get("clusters") or []
    print(f"  {model:16} {out['seconds']:6.1f}s  verdict={r.get('verdict')!r} "
          f"score={r.get('overall_coherence_score')}")
    print(f"      global issues ({len(issues)}):")
    for i in issues[:3]:
        print(f"        - {str(i)[:96]}")
    if per_cluster:
        low = [c for c in per_cluster if isinstance(c, dict) and (c.get("score") or 100) < 60]
        print(f"      per-cluster rows: {len(per_cluster)}, flagged below 60: {len(low)}")
        for c in low[:3]:
            print(f"        - n={c.get('n')} score={c.get('score')} "
                  f"rec={c.get('rec')} issue={str(c.get('issue'))[:60]}")
    print()
