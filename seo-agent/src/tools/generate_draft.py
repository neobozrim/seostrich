from __future__ import annotations

from .. import llm
from .. import memory


SYSTEM_PROMPT = """You are an expert SEO content writer with deep E-E-A-T awareness.
Write a comprehensive, well-researched article optimized for both search engines and AI citations.

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
  ],
  "structured_data_type": "Article|Recipe|HowTo|FAQPage|Review",
  "structured_data_template": {
    "@context": "https://schema.org",
    "@type": "...",
    "headline": "...",
    "description": "..."
  },
  "eeat_signals_included": [
    "first-hand experience",
    "authoritative citations",
    "author expertise signals"
  ],
  "og_image_suggestion": "description of recommended image for og:image"
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
- Write factual, quotable statements for AI citations

E-E-A-T writing guidelines:
- Include first-hand experience language: "In our experience...", "We've found that...",
  "Based on testing...", "From working with..."
- Add specific data points, statistics, or case studies with numbers
- Cite authoritative sources with links (studies, official documentation, industry reports)
- Include author expertise signals (mention credentials, years of experience, methodology)
- Write unique insights not found elsewhere — avoid rehashing top-ranking content
- Be transparent about how information was gathered or tested
- Use concrete, verifiable claims over vague assertions

Structured data template guidance:
- Guide/general content → Article schema
- Recipe content → Recipe schema (ingredients, steps, nutrition)
- Tutorial/how-to content → HowTo schema (steps, tools, supplies)
- FAQ-heavy content → FAQPage schema (question/answer pairs)
- Product review content → Review schema (itemReviewed, rating, author)
- Always include @context, @type, headline, description, author, datePublished
- Include image, publisher, and mainEntityOfPage where appropriate"""


def generate_draft(
    article_title: str,
    primary_keyword: str,
    secondary_keywords: list[str],
    content_type: str = "guide",
    target_words: int = 1500,
    angle: str = "",
    previous_draft: str = "",
    critique: str = "",
) -> dict:
    """Generate article draft for a calendar item.

    Args:
        article_title: Working title for the article.
        primary_keyword: Main target keyword.
        secondary_keywords: Supporting keywords to weave in.
        content_type: Type of content (guide, recipe, tutorial, review, listicle, faq).
        target_words: Target word count.
        angle: Editorial angle or hook.
        previous_draft: Previous draft markdown (for iterative refinement).
        critique: Feedback from preflight review to incorporate.
    """
    # Read brand constraints from memory blackboard
    brand_constraints = memory.read_brand_constraints()

    user_msg = f"""Write an article:
Title: {article_title}
Primary Keyword: {primary_keyword}
Secondary Keywords: {', '.join(secondary_keywords)}
Content Type: {content_type}
Target Word Count: {target_words}
Angle: {angle or 'Comprehensive, actionable guide'}

Write a complete, well-researched article that demonstrates strong E-E-A-T signals:
- Use first-hand experience language ("In our experience...", "We've found that...")
- Include specific data points, statistics, or case studies
- Cite authoritative sources with links
- Include author expertise signals
- Write unique insights not found elsewhere

Choose the appropriate structured data schema type based on the content_type:
- guide → Article
- recipe → Recipe
- tutorial → HowTo
- faq → FAQPage
- review → Review
Include a complete structured data template in the output.

Suggest an og:image that would be compelling for social sharing (1200x630px, relevant to topic)."""

    # Inject brand voice constraints if available
    if brand_constraints and brand_constraints.strip():
        user_msg += f"""

BRAND VOICE CONSTRAINTS — follow these strictly:
{brand_constraints}"""

    # Handle iterative refinement
    if previous_draft and critique:
        user_msg += f"""

ITERATIVE REFINEMENT — improve the previous draft based on critique:

PREVIOUS DRAFT:
{previous_draft}

CRITIQUE / FEEDBACK TO ADDRESS:
{critique}

Rewrite the article addressing all critique points while preserving what worked well.
Strengthen any weak E-E-A-T signals identified in the critique."""
    elif previous_draft:
        user_msg += f"""

ITERATIVE REFINEMENT — improve the previous draft:

PREVIOUS DRAFT:
{previous_draft}

Polish and enhance the draft while preserving its strengths."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.5, max_tokens=8000)
    return llm.parse_json_response(resp)
