from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an SEO strategist. Analyze the business description and extract keyword seeds for content research.

Output JSON format:
{
  "business_seeds": ["seed1", "seed2"],
  "site_seeds": ["seed1"],
  "competitor_seeds": ["seed1"],
  "notes": "brief rationale"
}

Rules:
- Extract 2-4 seeds per category (business, site, competitor)
- Seeds should be specific, searchable phrases (2-4 words)
- Focus on user intent: what problems do users search for?
- Include both product features and use cases
- Avoid brand names unless they're industry terms
- Use natural language users would search for"""


def extract_seeds(business_description: str, site_description: str = "", competitor_urls: list[str] = None) -> dict:
    """Extract keyword seeds from business description."""
    user_msg = f"""Business Description:
{business_description}

Site Description:
{site_description or "Not provided"}

Competitor URLs:
{chr(10).join(competitor_urls or [])}

Extract keyword seeds for SEO research."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
    return llm.parse_json_response(resp)
