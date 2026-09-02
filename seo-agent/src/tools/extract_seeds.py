from __future__ import annotations

from .. import llm
from ..config import settings

# max_tokens here is a sanity cap, not a latency control: reasoning tokens are
# not bounded by it (measured 2026-09-01 — a 2500-token cap did not stop a
# 10,358-token completion). Latency is governed by model choice.


SYSTEM_PROMPT = """You are an SEO strategist. Analyze the business description and extract keyword seeds for content research.

Output JSON format:
{
  "business_name": "the business's proper name, 1-4 words, as it would appear as a page title",
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

    # Fast model: this node is extraction, and it kept the brief's own phrasing
    # verbatim ("agentic commerce building blocks", "hands-on AI building")
    # where the reasoning model generalised it away — 28s vs 44s, and better
    # seeds, measured 2026-09-01. The seeds decide what the whole strategy is
    # about, so preserving the user's own words matters more here than depth.
    resp = llm.chat(
        user_msg, system=SYSTEM_PROMPT, temperature=0.3,
        max_tokens=800, model=settings.qwen_model_fast,
    )
    return llm.parse_json_response(resp)
