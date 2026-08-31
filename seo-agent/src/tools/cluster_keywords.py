from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an SEO content strategist. Group keywords into thematic clusters based on search intent and topic similarity.

Output JSON format:
{
  "clusters": [
    {
      "cluster_id": 1,
      "cluster_name": "name",
      "head_term": "primary keyword",
      "keywords": ["kw1", "kw2"],
      "intent": "informational|commercial|transactional",
      "avg_volume": 1000,
      "avg_difficulty": 45,
      "rationale": "why these keywords belong together"
    }
  ]
}

Rules:
- Create the requested number of clusters (typically 5-10)
- When asked for 8+, OVER-GENERATE: capture more themes than will ultimately be pursued; a later selection step cuts the weak ones — do not pre-filter
- Each cluster should have 3-15 keywords
- Head term should be the highest-volume, most specific keyword
- Group by user intent AND topic similarity
- Separate informational from commercial/transactional intent
- Cluster names should be descriptive and actionable
- Include rationale for each cluster"""


def cluster_keywords(
    keywords: list[dict],
    max_clusters: int = 10,
    location_code: int | None = None,
    language_code: str | None = None,
) -> dict:
    """Cluster keywords into thematic groups."""
    # Format keywords for LLM
    kw_text = "\n".join([
        f"- {k.get('keyword', '')} (volume: {k.get('volume', 0)}, difficulty: {k.get('difficulty', 0)}, intent: {k.get('intent', 'unknown')})"
        for k in keywords[:150]  # Limit to top 150
    ])

    market_line = ""
    if location_code:
        market_line = f"\nTarget market: location_code {location_code}" + (f", language {language_code}" if language_code else "") + "."

    user_msg = f"""Keywords to cluster:
{kw_text}
{market_line}
Create {max_clusters} thematic clusters."""

    try:
        resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
        result = llm.parse_json_response(resp)
        if result and (isinstance(result, dict) or isinstance(result, list)):
            return {"success": True, "clusters": result}
        return {"success": False, "error": "LLM returned invalid cluster format", "clusters": None}
    except Exception as e:
        return {"success": False, "error": f"LLM clustering failed: {str(e)}", "clusters": None}
