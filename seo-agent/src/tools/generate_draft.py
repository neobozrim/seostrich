from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an expert SEO content writer. Write a comprehensive, well-researched article optimized for both search engines and AI citations.

Output JSON format:
{
  "title": "SEO-optimized title (50-60 chars)",
  "meta_description": "Compelling meta (150-160 chars)",
  "slug": "url-friendly-slug",
  "content": "full article in markdown",
  "word_count": 1500,
  "internal_links": ["suggested internal link anchors"],
  "external_sources": ["sources to cite"],
  "faq": [
    {"question": "Q", "answer": "A"}
  ]
}

Writing rules:
- Lead with value: answer the search query in first 2-3 paragraphs
- Use clear H2/H3 hierarchy
- Include primary keyword in first 100 words, H1, meta
- Keyword density: 1-2% (natural usage)
- Write in short paragraphs (2-4 sentences)
- Include specific examples, data, or case studies
- Add FAQ section with 3-5 common questions
- Use bullet points and numbered lists for scannability
- End with clear call-to-action or next steps
- Cite authoritative sources (.edu, .gov, industry reports)
- Write factual, quotable statements for AI citations"""


def generate_draft(
    article_title: str,
    primary_keyword: str,
    secondary_keywords: list[str],
    content_type: str = "guide",
    target_words: int = 1500,
    angle: str = "",
) -> dict:
    """Generate article draft for a calendar item."""
    user_msg = f"""Write an article:
Title: {article_title}
Primary Keyword: {primary_keyword}
Secondary Keywords: {', '.join(secondary_keywords)}
Content Type: {content_type}
Target Word Count: {target_words}
Angle: {angle or 'Comprehensive, actionable guide'}

Write a complete, well-researched article."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.5, max_tokens=8000)
    return llm.parse_json_response(resp)
