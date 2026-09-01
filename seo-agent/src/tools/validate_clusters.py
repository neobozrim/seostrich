"""Validate keyword clusters for coherence — reflection step after cluster_keywords.

This is the "wait, are these clusters actually coherent?" self-check.
Runs after cluster_keywords to catch meaningless groupings before they
propagate into pillar recommendations and content calendars.
"""
from __future__ import annotations

import json

from .. import llm


SYSTEM_PROMPT = """You are a senior SEO strategist reviewing keyword clusters produced by an automated clustering algorithm.

Your job is to evaluate whether the clusters make strategic sense BEFORE they become content pillars.

**Evaluate each cluster on:**
1. **Thematic coherence** — Do the keywords in this cluster share a clear, specific theme? Or are they loosely related terms forced together?
2. **Distinctiveness** — Is this cluster genuinely different from the other clusters? Or does it overlap significantly with another?
3. **Content viability** — Can a single content pillar or article series realistically cover this cluster? Or is it too broad/narrow?
4. **Search intent alignment** — Do the keywords share similar search intent (informational, transactional, navigational)? Or are intents mixed in ways that would make content unfocused?
5. **Strategic value** — Does this cluster serve a clear business goal? Or is it keyword stuffing disguised as strategy?

**Be ruthlessly honest.** Bad clusters lead to bad pillars lead to bad content. It's better to flag problems now than publish content nobody wants.

**Common problems to catch:**
- "Catch-all" clusters that group unrelated keywords just because they're about the same broad topic
- Clusters that are too narrow (1-2 keywords) — these should be merged or dropped
- Clusters that overlap >40% in intent with another cluster — recommend merging
- Clusters that target mixed intents (e.g., "buy X" + "what is X" in same cluster)
- Clusters based on keyword volume alone without strategic coherence

**Output format** — keep it TIGHT. Refer to clusters by their number.
Never repeat keyword text back; it is already known.
```json
{
  "overall_coherence_score": 0-100,
  "verdict": "approved|needs_revision|rejected",
  "clusters": [
    {"n": 1, "score": 0-100, "rec": "keep|merge|split|drop", "issue": "one short phrase, or \"\""}
  ],
  "global_issues": ["at most 3 short cross-cluster problems"],
  "missing_themes": ["at most 3 themes that deserve their own cluster"]
}
```

**Verdict criteria:**
- approved: overall_coherence_score >= 75, no cluster below 60
- needs_revision: overall_coherence_score 50-74, or 1-2 clusters below 60
- rejected: overall_coherence_score < 50, or 3+ clusters below 60
"""


def validate_clusters(
    clusters: dict,
    seeds: dict | None = None,
    domain: str = "",
    domain_description: str = "",
) -> dict:
    """Validate keyword clusters for coherence before they become pillars.

    Args:
        clusters: Output from cluster_keywords — dict of cluster_name -> [keywords]
        seeds: Original seed keywords (optional, for context)
        domain: Site domain for strategic context
        domain_description: Brief description of what the site/business does
    """
    if not clusters:
        return {
            "overall_coherence_score": 0,
            "verdict": "rejected",
            "clusters": [],
            "global_issues": ["No clusters provided — nothing to validate"],
            "missing_themes": [],
            "action_items": ["Run cluster_keywords first"],
        }

    cluster_summary = []
    for idx, (name, keywords) in enumerate(clusters.items(), 1):
        cluster_summary.append({
            "n": idx,
            "name": name,
            "keywords": keywords[:12],  # Cap to avoid token bloat
            "keyword_count": len(keywords),
        })

    seed_list = []
    if seeds:
        for category, kws in seeds.items():
            seed_list.extend(kws if isinstance(kws, list) else [kws])

    prompt = f"""Validate these keyword clusters for coherence and strategic value.

**Domain:** {domain or "not specified"}
**Business:** {domain_description or "not specified"}
**Original seeds:** {json.dumps(seed_list[:30]) if seed_list else "not provided"}

**Clusters to validate:**
{json.dumps(cluster_summary, indent=2, ensure_ascii=False)}

Total clusters: {len(clusters)}
Total keywords: {sum(len(kws) for kws in clusters.values())}

Evaluate each cluster and provide your verdict."""

    # Only `verdict` and `global_issues` are consumed by the strategy graph, so
    # the schema above is deliberately compact. The old one asked for per-cluster
    # issue lists plus `revised_keywords` (full keyword text echoed back) — all
    # discarded, but all paid for in output tokens, which is what pushes a call
    # past its deadline. 1500 tokens is ample for the tight form; 300s leaves
    # headroom instead of sitting under the ~121s a 4000-token reply needs.
    raw = llm.chat(
        prompt,
        system=SYSTEM_PROMPT,
        max_tokens=1500,
        timeout=300.0,
    )

    result = llm.parse_json_response(raw)
    if not result:
        return {
            "overall_coherence_score": -1,
            "verdict": "error",
            "clusters": [],
            "global_issues": ["LLM failed to produce valid JSON validation"],
            "missing_themes": [],
            "action_items": ["Retry validation"],
            "raw_response": raw[:500],
        }

    return result
