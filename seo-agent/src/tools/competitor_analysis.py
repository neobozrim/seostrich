from __future__ import annotations

from .. import llm
from . import dataforseo as dfs
from .site_scraper import scrape_site


def analyze_competitor(
    competitor_url: str,
    our_domain: str = "",
    our_description: str = "",
) -> dict:
    """Reverse-engineer a competitor's SEO strategy and compare with ours."""
    # 1. Get their top keywords from DataForSEO
    try:
        their_keywords = dfs.keywords_for_site(competitor_url, limit=50)
    except Exception:
        their_keywords = []

    # 2. Scrape a few of their pages for content analysis
    site_data = scrape_site(competitor_url, max_pages=5)

    # 3. Get keyword gaps (what they rank for that we don't)
    gap_keywords = []
    if our_domain:
        try:
            gap_keywords = dfs.domain_intersection(our_domain, competitor_url, limit=50)
        except Exception:
            pass

    # 4. LLM analysis
    system = """You are an SEO strategist analyzing a competitor's content strategy.
Compare their approach with ours and identify opportunities.

Output JSON:
{
  "competitor_summary": "overview of their strategy",
  "content_themes": ["theme1", "theme2"],
  "top_keywords": ["kw1", "kw2"],
  "content_gaps": ["what they cover that we don't"],
  "opportunities": ["what we could do better"],
  "differentiation": "how we can stand out",
  "adopt_or_avoid": [
    {"tactic": "tactic name", "verdict": "adopt|adapt|avoid", "reason": "why"}
  ]
}"""

    user_msg = f"""Competitor URL: {competitor_url}
Their top keywords: {llm.format_json(their_keywords[:20])}
Pages scraped: {llm.format_json(site_data.get('pages', [])[:5])}
Keyword overlap with us: {llm.format_json(gap_keywords[:20])}

Our business: {our_description}

Analyze their strategy and find opportunities."""

    resp = llm.chat(user_msg, system=system, temperature=0.3)
    result = llm.parse_json_response(resp)
    result["raw_data"] = {
        "keywords_count": len(their_keywords),
        "pages_scraped": site_data.get("pages_scraped", 0),
        "gap_keywords": len(gap_keywords),
    }
    return result


def compare_strategies(
    our_strategy: dict,
    competitor_strategy: dict,
) -> dict:
    """Compare our SEO strategy with a competitor's (or Manus agent output)."""
    system = """You are an SEO strategist comparing two content strategies.
Identify strengths, weaknesses, and recommendations.

Output JSON:
{
  "comparison": "overall comparison",
  "our_strengths": ["strength1"],
  "our_weaknesses": ["weakness1"],
  "their_strengths": ["strength1"],
  "their_weaknesses": ["weakness1"],
  "gaps_to_close": ["what we need to add"],
  "unique_advantages": ["what only we have"],
  "action_items": ["specific next steps"]
}"""

    user_msg = f"""Our strategy:
{llm.format_json(our_strategy)}

Competitor strategy:
{llm.format_json(competitor_strategy)}

Compare and provide recommendations."""

    resp = llm.chat(user_msg, system=system, temperature=0.3)
    return llm.parse_json_response(resp)
