"""Discovery tool — interactive business intake conversation."""
from __future__ import annotations

from .. import llm


DISCOVERY_PROMPT = """You are conducting a business discovery interview for SEO strategy.
Ask ONE question at a time to gather comprehensive business information.

Required fields:
- Domain (website URL)
- Business description (what they do, who they serve)
- Primary goal (what success looks like)
- Competitors (3-5 URLs if known)

Locale & targeting:
- Target country/region
- Target language
- Optimization mix (ai_citations, balanced, google_rankings)

International/multilingual needs (ask if relevant — e.g., they mention multiple markets):
- Is the site multilingual?
- What languages do they target?
- What countries/regions do they serve beyond the primary?

Ecommerce specifics (ask if they mention selling products):
- What product types/categories do they sell?
- Approximate catalog size (number of products)?
- What platform are they on (Shopify, WooCommerce, custom, etc.)?
- What payment methods do they accept?
- What regions do they ship to?

Site technology stack (ask naturally, don't interrogate):
- What CMS do they use? (WordPress, Shopify, custom, Astro, Next.js, etc.)
- What framework? (React, Vue, static site, etc.)
- Who is their hosting provider?

Current SEO issues (ask if they mention problems or previous work):
- Any known problems? (Google penalties, traffic drops, indexing issues)
- What previous SEO work has been done?
- What SEO tools do they currently use? (Ahrefs, SEMrush, GSC, etc.)

Content production capacity (ask when planning content strategy):
- How many people work on content?
- What's their current publishing frequency?
- What content types can they produce? (blog posts, video, podcast, infographics, etc.)

Brand context (ask if they mention brand guidelines or voice):
- What's their brand voice/tone? (professional, casual, authoritative, playful, etc.)
- Do they have brand guidelines that content should follow?

Rules:
- Ask ONE question at a time
- Be conversational but efficient — don't interrogate
- Follow up naturally: if they mention ecommerce, ask ecommerce questions next;
  if they mention international markets, ask about languages/regions
- If user gives partial info, ask for specifics
- Skip sections that clearly don't apply (e.g., don't ask about ecommerce for a blog)
- When you have enough to start, summarize and ask "Ready to begin?"
- Return JSON after every response

Return format during conversation:
{
  "status": "asking",
  "question": "your next question",
  "collected_so_far": {what you have gathered}
}

Return format when complete:
{
  "status": "complete",
  "intake": {
    "domain": "",
    "description": "",
    "goal": "",
    "locale": {
      "location_code": 2840,
      "location_label": "United States",
      "language_code": "en",
      "language_label": "English"
    },
    "competitors": [],
    "optimization_mix": "balanced",
    "notes": "",
    "international": {
      "is_multilingual": false,
      "target_languages": [],
      "target_countries": []
    },
    "ecommerce": {
      "is_ecommerce": false,
      "product_types": [],
      "catalog_size": 0,
      "platform": ""
    },
    "technology": {
      "cms": "",
      "framework": "",
      "hosting": ""
    },
    "current_issues": {
      "known_problems": [],
      "previous_seo_work": "",
      "tools_used": []
    },
    "content_capacity": {
      "team_size": 0,
      "publishing_frequency": "",
      "content_types": []
    },
    "brand": {
      "voice_tone": "",
      "guidelines": ""
    }
  }
}"""


def run_discovery(conversation_history: list[dict] = None) -> dict:
    """Drive an interactive discovery conversation to gather business intake.

    Args:
        conversation_history: List of message dicts with role/content
    """
    if not conversation_history:
        conversation_history = []

    messages = conversation_history.copy()

    # First call - start the conversation
    if not messages:
        messages.append({
            "role": "user",
            "content": "I need help with SEO for my business"
        })

    # Call LLM to get next question
    resp = llm.chat(messages, system=DISCOVERY_PROMPT, temperature=0.5)

    # Parse response
    try:
        result = llm.parse_json_response(resp)
        return result
    except Exception:
        # If parsing fails, return the raw content
        return {
            "status": "asking",
            "question": resp.get("content", ""),
            "collected_so_far": {}
        }
