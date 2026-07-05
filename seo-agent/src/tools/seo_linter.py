from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an SEO auditor. Score an article's on-page SEO and identify specific improvements.

Output JSON format:
{
  "score": 75,
  "checks": [
    {
      "category": "title|meta|headings|keywords|content|links|technical",
      "status": "pass|fail|warning",
      "description": "what was checked",
      "details": "specific findings",
      "recommendation": "how to improve (if needed)"
    }
  ],
  "top_improvements": ["most important fixes"]
}

Check for:
- Title tag (50-60 chars, includes primary keyword)
- Meta description (150-160 chars, compelling)
- H1 tag (single, includes keyword)
- Heading hierarchy (no skipped levels)
- Keyword in first 100 words
- Keyword density (1-2%)
- Internal links (3-5 relevant links)
- External citations (2-3 authoritative sources)
- Content length (matches target)
- Readability (short paragraphs, bullet points)
- FAQ section for AI citations
- Slug format (lowercase, hyphens)
- Image alt text (if images mentioned)"""


def seo_linter(article: dict) -> dict:
    """Lint article for on-page SEO."""
    user_msg = f"""Audit this article for SEO:
{llm.format_json(article)}

Score and identify improvements."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
    return llm.parse_json_response(resp)
