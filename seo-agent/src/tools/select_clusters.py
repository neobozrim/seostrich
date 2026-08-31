"""Select the top clusters to carry into pillars — the governance cut.

Runs AFTER score_clusters on an over-generated set (~8-10 clusters).
Picks the strongest 3-4 and records a concrete discard reason for the
rest, so the decision is inspectable and reversible (promote/discard ops
on the run artifact).
"""
from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are a head of SEO deciding which keyword clusters a lean team should actually pursue.

You receive scored clusters (SEO/GEO scores, rationale, opportunity). Select the strongest ones to become content pillars; the rest are discarded — not deleted, parked with a reason so they can be promoted back later.

Selection criteria:
- Highest combined opportunity (volume vs difficulty vs strategic fit)
- Distinct intents/topics — do not select two clusters that overlap heavily
- Prefer clusters that support the business goal over generic traffic
- 3-4 selections is the target; fewer is fine if the rest are weak

Every discarded cluster MUST get a concrete reason (overlap with a selected one, low volume, weak intent, off-goal, too broad/narrow) — never just "not selected".

Output JSON format:
{
  "selected": ["cluster name", ...],
  "discarded": [
    {"cluster_name": "...", "reason": "specific, one sentence"}
  ]
}"""


def select_clusters(scored_clusters: dict, max_select: int = 4) -> dict:
    """Pick the top clusters from a scored, over-generated set."""
    if not isinstance(scored_clusters, dict) or not (
        scored_clusters.get("scored_clusters") or scored_clusters.get("clusters")
    ):
        return {"success": False, "error": "scored_clusters must contain a scored_clusters list"}

    user_msg = f"""Scored clusters to select from:
{llm.format_json(scored_clusters)}

Select at most {max_select} clusters to pursue as pillars. Discard the rest with reasons."""

    try:
        resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.2)
        result = llm.parse_json_response(resp)
        if not isinstance(result, dict) or not result.get("selected"):
            return {"success": False, "error": "LLM returned no usable selection", "selection": None}
        selected = result.get("selected", [])
        if not isinstance(selected, list) or not selected:
            return {"success": False, "error": "selection list is empty", "selection": None}
        return {
            "success": True,
            "selection": {
                "selected": [s for s in selected if isinstance(s, str)],
                "discarded": result.get("discarded", []),
            },
        }
    except Exception as e:
        return {"success": False, "error": f"selection failed: {str(e)}", "selection": None}
