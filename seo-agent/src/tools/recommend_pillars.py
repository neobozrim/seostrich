from __future__ import annotations

from .. import llm

# max_tokens here is a sanity cap, not a latency control: reasoning tokens are
# not bounded by it (measured 2026-09-01 — a 2500-token cap did not stop a
# 10,358-token completion). Latency is governed by model choice.


SYSTEM_PROMPT = """You are an SEO strategist. Select the best clusters to become content pillars based on opportunity scores and strategic fit.

Output JSON format:
{
  "pillars": [
    {
      "cluster_id": 1,
      "cluster_name": "name",
      "pillar_title": "Comprehensive Guide to X",
      "pillar_type": "hub|guide|comparison",
      "priority": 1,
      "rationale": "why this is a top pillar"
    }
  ],
  "skipped": [
    {
      "cluster_id": 5,
      "reason": "why skipped"
    }
  ]
}

Rules:
- Select 3-5 pillars
- Prioritize by combined_score (highest first)
- Pillar titles should be compelling and comprehensive
- Include mix of pillar types if appropriate
- Explain why each pillar was selected or skipped
- Priority 1 = highest priority pillar"""


def recommend_pillars(scored_clusters: dict) -> dict:
    """Recommend which clusters should become content pillars."""
    user_msg = f"""Select content pillars from these scored clusters:
{llm.format_json(scored_clusters)}

Recommend 3-5 pillars with priority ranking."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3, max_tokens=2500)
    return llm.parse_json_response(resp)
