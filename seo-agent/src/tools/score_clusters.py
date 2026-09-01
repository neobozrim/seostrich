from __future__ import annotations

from .. import llm

# Budget sized to what this node emits (a score row per cluster); the deadline in
# llm.timeout_for() is derived from it, so an unbounded budget means an
# unmeetable deadline.


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

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3, max_tokens=2000)
    return llm.parse_json_response(resp)
