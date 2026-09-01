"""Select the top clusters to carry into pillars — the governance cut.

Runs AFTER score_clusters on an over-generated set (~8-10 clusters).
Picks the strongest 3-4 and records a concrete discard reason for the
rest, so the decision is inspectable and reversible (promote/discard ops
on the run artifact).
"""
from __future__ import annotations

from .. import llm

# max_tokens here is a sanity cap, not a latency control: reasoning tokens are
# not bounded by it (measured 2026-09-01 — a 2500-token cap did not stop a
# 10,358-token completion). Latency is governed by model choice.


SYSTEM_PROMPT = """You are a head of SEO deciding which keyword clusters a lean team should actually pursue.

You are told what the business is. You receive clusters with a `metrics` block measured from real DataForSEO data (total_volume, avg_difficulty, avg_cpc, commercial_share, top_keywords) plus an `opportunity` label produced by a stated rule. These are measurements, not estimates. Select the ones to become content pillars; the rest are discarded — not deleted, parked with a reason so they can be promoted back later.

When you cite a number, cite one from the metrics block. Do not invent scores.

Selection criteria, in strict priority order:
1. RELEVANCE TO THE BUSINESS is the hard gate. A cluster only qualifies if it directly serves what this business is, does, or sells — or what its real audience would search for in relation to it. Reject any cluster that is merely adjacent, tangential, or generic, no matter how high its volume or how good its scores. High volume on an off-topic cluster is worthless to this client: it attracts the wrong audience.
2. Among the RELEVANT clusters, prefer the best opportunity (volume vs difficulty vs strategic fit). In thin/niche markets a low-volume but tightly relevant cluster beats a high-volume irrelevant one.
3. Distinct intents/topics — do not select two clusters that overlap heavily.
4. 3-4 selections is the target; fewer is fine if the rest are off-topic or weak. If almost nothing is relevant, select the single closest match rather than padding with off-topic volume.

Every discarded cluster MUST get a concrete reason. For off-topic clusters the reason must say they are not relevant to THIS business (e.g. "off-topic: e-book platform, not poetry performance"). Other valid reasons: overlap with a selected cluster, weak intent, too broad/narrow. Never just "not selected", and never discard a tightly relevant cluster purely because another cluster has more volume.

EVERY cluster, selected or discarded, must carry a one-sentence reason. A user
reading this later needs to know why each pillar was chosen, not only why the
others were dropped. For selected clusters say what it wins for THIS business
(the audience it serves, the intent it captures, the angle it owns) — not just
"high score".

Output JSON format:
{
  "selected": [
    {"cluster_name": "...", "reason": "why this one earns a pillar, one sentence"}
  ],
  "discarded": [
    {"cluster_name": "...", "reason": "specific, one sentence"}
  ]
}"""


def select_clusters(scored_clusters: dict, max_select: int = 4, business_description: str = "") -> dict:
    """Pick the top clusters from a scored, over-generated set.

    ``business_description`` is required for the relevance gate — without it the
    LLM can only rank by volume/opportunity and drifts toward off-topic traffic.
    """
    if not isinstance(scored_clusters, dict) or not (
        scored_clusters.get("scored_clusters") or scored_clusters.get("clusters")
    ):
        return {"success": False, "error": "scored_clusters must contain a scored_clusters list"}

    biz = (business_description or "").strip()
    biz_block = f"The business this strategy is for:\n{biz}\n\n" if biz else ""
    user_msg = f"""{biz_block}Scored clusters to select from:
{llm.format_json(scored_clusters)}

Select at most {max_select} clusters to pursue as pillars. Relevance to the business is the hard gate. Discard the rest with reasons. Give a reason for the selected ones too."""

    try:
        resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.2, max_tokens=1500)
        result = llm.parse_json_response(resp)
        if not isinstance(result, dict) or not result.get("selected"):
            return {"success": False, "error": "LLM returned no usable selection", "selection": None}
        selected = result.get("selected", [])
        if not isinstance(selected, list) or not selected:
            return {"success": False, "error": "selection list is empty", "selection": None}

        # Accept either [{cluster_name, reason}] or the older bare ["name"]
        # form, so a model that ignores the schema still yields a selection.
        names: list[str] = []
        reasons: list[dict] = []
        for entry in selected:
            if isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
                reasons.append({"cluster_name": entry.strip(), "reason": ""})
            elif isinstance(entry, dict):
                name = entry.get("cluster_name") or entry.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
                    reasons.append({
                        "cluster_name": name.strip(),
                        "reason": str(entry.get("reason", ""))[:300],
                    })
        if not names:
            return {"success": False, "error": "selection list is empty", "selection": None}
        return {
            "success": True,
            "selection": {
                "selected": names,
                "selected_reasons": reasons,
                "discarded": result.get("discarded", []),
            },
        }
    except Exception as e:
        return {"success": False, "error": f"selection failed: {str(e)}", "selection": None}
