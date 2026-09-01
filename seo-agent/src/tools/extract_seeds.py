from __future__ import annotations

from .. import llm

# Budget sized to what this node emits (~12 seeds plus a one-line note); the deadline in
# llm.timeout_for() is derived from it, so an unbounded budget means an
# unmeetable deadline.


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
- Use natural language users would search for
- CRITICAL for non-English markets: write seeds in the language the target
  market actually searches in, and keep any native-language terms from the
  brief VERBATIM (never translate or transliterate them). A local term like
  "моноспектакъл" is a far better seed than "Bulgarian monospectacle poet".
  Include both the native term and one or two local-language intent phrases."""


def extract_seeds(
    business_description: str,
    site_description: str = "",
    competitor_urls: list[str] = None,
    language_code: str = "",
) -> dict:
    """Extract keyword seeds from business description.

    ``language_code`` (e.g. "bg") is a hint so seeds come back in the market's
    own language rather than defaulting to English.
    """
    lang_hint = f"\nTarget search language: {language_code}" if language_code else ""
    user_msg = f"""Business Description:
{business_description}

Site Description:
{site_description or "Not provided"}

Competitor URLs:
{chr(10).join(competitor_urls or [])}{lang_hint}

Extract keyword seeds for SEO research."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3, max_tokens=800)
    return llm.parse_json_response(resp)
