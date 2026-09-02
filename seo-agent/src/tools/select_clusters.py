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

For each SELECTED cluster also describe it, because whoever reads this strategy
next has to act on it without seeing the keyword list:
- "what_it_is": one sentence naming the topic and WHO is searching it.
- "how_to_use_it": one sentence on the content play — the kind of page, and the
  angle that suits this business specifically.
Discarded clusters need only the reason; keep those short.

Output JSON format:
{
  "selected": [
    {"cluster_name": "...",
     "reason": "why this one earns a pillar, one sentence",
     "what_it_is": "the topic and who searches it, one sentence",
     "how_to_use_it": "the content play, one sentence"}
  ],
  "discarded": [
    {"cluster_name": "...", "reason": "specific, one sentence"}
  ]
}"""


def _for_selection(scored: dict) -> list[dict]:
    """What this node needs to judge relevance — and nothing else.

    score_clusters copies each cluster forward wholesale, so the payload also
    carried per-keyword stats, the full metrics block, and stale governance
    fields (discard_reason, discarded_at) left by earlier edits. Measured on a
    real run: 13 clusters produced a 25,804-character prompt, ~6,451 tokens, to
    answer "which of these serve this business".

    Trimming an INPUT to fit a node's prompt is a different thing from trimming
    the RESULT the agent reads. The judgement needs the topic, a sample of its
    keywords and the headline numbers; the complete data stays on the run for
    anyone who wants it.
    """
    entries = scored.get("scored_clusters") or scored.get("clusters") or []
    lean = []
    for i, c in enumerate(entries, 1):
        if not isinstance(c, dict):
            continue
        metrics = c.get("metrics") or {}
        keywords = [
            k.get("keyword") if isinstance(k, dict) else k
            for k in (c.get("keywords") or [])
        ]
        lean.append({
            "cluster_name": c.get("cluster_name") or c.get("name") or f"Cluster {i}",
            "head_term": c.get("head_term") or "",
            "intent": c.get("intent") or "",
            # enough to see what the cluster is actually ABOUT
            "example_keywords": [k for k in keywords if k][:8],
            "keyword_count": metrics.get("keyword_count", len(keywords)),
            "total_volume": metrics.get("total_volume", c.get("total_volume")),
            "avg_difficulty": metrics.get("avg_difficulty", c.get("avg_difficulty")),
            "avg_cpc": metrics.get("avg_cpc"),
            "commercial_share": metrics.get("commercial_share"),
            "opportunity": c.get("opportunity"),
            "why_these_group": c.get("rationale") or "",
        })
    return lean


# DataForSEO's smallest non-zero volume bucket is 10. A cluster whose BEST
# keyword sits in that bucket has no measurable demand: it is a handful of
# phrases nobody searches, and one of them will be a tagline or a stray brand
# query that the expansion dragged in. Such a cluster must not become a
# content pillar on the strength of "relevance" alone.
#
# The floor is relative, not absolute. In a genuinely thin market every
# cluster is under it, and discarding all of them would leave nothing — there
# the floor is waived and the fact is stated, so the report says "this market
# has no measurable demand" instead of manufacturing pillars.
DEMAND_FLOOR = 20


def _apply_demand_floor(scored: dict) -> tuple[dict, list[dict], str]:
    """Split clusters into (eligible-for-selection, pre-discarded, note)."""
    key = "scored_clusters" if scored.get("scored_clusters") else "clusters"
    clusters = scored.get(key) or []

    def max_vol(c: dict) -> int:
        m = c.get("metrics") or {}
        if m.get("max_volume") is not None:
            return int(m["max_volume"] or 0)
        return int(c.get("max_volume") or c.get("avg_volume") or 0)

    above = [c for c in clusters if max_vol(c) >= DEMAND_FLOOR]
    if not above or len(above) == len(clusters):
        note = "" if above else (
            f"thin market: no cluster has a keyword at or above {DEMAND_FLOOR} searches/month, "
            f"so the demand floor was waived and selection ran on relevance alone"
        )
        return scored, [], note

    dropped = []
    for c in clusters:
        if max_vol(c) >= DEMAND_FLOOR:
            continue
        m = c.get("metrics") or {}
        top = (m.get("top_keywords") or [{}])[0]
        name = c.get("cluster_name") or c.get("name") or ""
        dropped.append({
            "cluster_name": name,
            "reason": (
                f"no measurable search demand in this market: its best keyword "
                f"\"{top.get('keyword') or c.get('head_term') or '?'}\" has "
                f"{top.get('volume') or max_vol(c)} searches/month, under the "
                f"{DEMAND_FLOOR}/month floor — parked, not deleted; promote it back if "
                f"you want to build for it anyway"
            ),
            "demand_floor": True,
        })
    filtered = dict(scored)
    filtered[key] = above
    return filtered, dropped, ""


def select_clusters(scored_clusters: dict, max_select: int = 4, business_description: str = "") -> dict:
    """Pick the top clusters from a scored, over-generated set.

    ``business_description`` is required for the relevance gate — without it the
    LLM can only rank by volume/opportunity and drifts toward off-topic traffic.
    """
    if not isinstance(scored_clusters, dict) or not (
        scored_clusters.get("scored_clusters") or scored_clusters.get("clusters")
    ):
        return {"success": False, "error": "scored_clusters must contain a scored_clusters list"}

    # Enforced in code, before the model sees the candidates: a cluster with no
    # measurable demand cannot be selected however relevant it sounds.
    scored_clusters, floor_dropped, floor_note = _apply_demand_floor(scored_clusters)

    biz = (business_description or "").strip()
    biz_block = f"The business this strategy is for:\n{biz}\n\n" if biz else ""
    user_msg = f"""{biz_block}Scored clusters to select from:
{llm.format_json(_for_selection(scored_clusters))}

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
                        "what_it_is": str(entry.get("what_it_is", ""))[:300],
                        "how_to_use_it": str(entry.get("how_to_use_it", ""))[:300],
                    })
        if not names:
            return {"success": False, "error": "selection list is empty", "selection": None}
        discarded = list(result.get("discarded", []) or []) + floor_dropped
        selection = {
            "selected": names,
            "selected_reasons": reasons,
            "discarded": discarded,
        }
        if floor_note:
            selection["note"] = floor_note
        return {"success": True, "selection": selection}
    except Exception as e:
        return {"success": False, "error": f"selection failed: {str(e)}", "selection": None}
