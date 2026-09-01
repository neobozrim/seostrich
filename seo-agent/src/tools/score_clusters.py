from __future__ import annotations

from .. import llm
from ..config import settings

# max_tokens here is a sanity cap, not a latency control: reasoning tokens are
# not bounded by it (measured 2026-09-01 — a 2500-token cap did not stop a
# 10,358-token completion). Latency is governed by model choice.


SYSTEM_PROMPT = """You are an SEO analyst. Score each keyword cluster on SEO opportunity and GEO (AI citation) opportunity.

Output JSON format:
{
  "scored_clusters": [
    {
      "cluster_id": 1,
      "cluster_name": "name",
      "seo_score": 75,
      "geo_score": 65,
      "combined_score": 70,
      "seo_rationale": "why this SEO score",
      "geo_rationale": "why this GEO score",
      "opportunity": "high|medium|low"
    }
  ]
}

Scoring criteria:
SEO Score (0-100):
- High volume, low difficulty = high score
- Clear commercial intent = higher score
- Multiple related keywords = higher score

GEO Score (0-100):
- Informational, educational content = higher score
- Topics AI can cite = higher score
- Specific, factual topics = higher score
- Avoids opinion/subjective = higher score

Combined Score: weighted average (0.6 SEO + 0.4 GEO)"""


def score_clusters(clusters: dict) -> dict:
    """Score clusters for SEO and GEO opportunity."""
    user_msg = f"""Score these keyword clusters:
{llm.format_json(clusters)}

Provide SEO, GEO, and combined scores."""

    # Fast model: this node is arithmetic over cluster stats, no judgment.
    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3, max_tokens=2000, model=settings.qwen_model_fast)
    return llm.parse_json_response(resp)
