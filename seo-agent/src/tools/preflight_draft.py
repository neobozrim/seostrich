from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an SEO editor. Review an article before publishing and identify issues or improvements.

Output JSON format:
{
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "keyword|structure|content|technical",
      "description": "what's wrong",
      "fix": "how to fix it",
      "location": "section or paragraph"
    }
  ],
  "ready_to_publish": true/false,
  "summary": "overall assessment"
}

Check for:
- Keyword placement (title, H1, first 100 words, meta)
- Keyword density (1-2% target)
- Heading structure (single H1, logical H2/H3 hierarchy)
- Internal linking opportunities
- External citations (authoritative sources)
- Content depth and accuracy
- Readability (short paragraphs, bullet points)
- FAQ section for AI citations
- Meta description quality
- Slug format (lowercase, hyphens)"""


def preflight_draft(draft: dict) -> dict:
    """Pre-flight checklist for article draft."""
    user_msg = f"""Review this article draft:
{llm.format_json(draft)}

Identify issues and improvements before publishing."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
    return llm.parse_json_response(resp)
