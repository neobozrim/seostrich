from __future__ import annotations

from datetime import datetime, timedelta

from .. import llm


SYSTEM_PROMPT = """You are a content strategist. Create a content calendar with specific article plans based on content pillars.

Output JSON format:
{
  "calendar": [
    {
      "week": 1,
      "publish_date": "2026-07-15",
      "pillar_id": 1,
      "article_title": "specific title",
      "primary_keyword": "main keyword",
      "secondary_keywords": ["kw1", "kw2"],
      "content_type": "guide|howto|listicle|comparison|case-study",
      "target_words": 1500,
      "angle": "unique angle or hook",
      "notes": "additional guidance"
    }
  ]
}

Rules:
- Plan 4-8 weeks of content
- 1-2 articles per week
- Distribute across pillars evenly
- Vary content types
- Include seasonal/trending topics when relevant
- Target word counts: guides 2000+, howtos 1200-1500, listicles 1000-1500
- Each article should target specific keywords from its pillar"""


def plan_calendar(pillars: dict, weeks: int = 6, articles_per_week: int = 1) -> dict:
    """Create content calendar from pillars."""
    start_date = datetime.now() + timedelta(days=7)
    
    user_msg = f"""Create a {weeks}-week content calendar:
Pillars: {llm.format_json(pillars)}

Start date: {start_date.strftime('%Y-%m-%d')}
Articles per week: {articles_per_week}

Plan specific article topics for each week."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.4)
    return llm.parse_json_response(resp)
