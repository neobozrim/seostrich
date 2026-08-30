from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are an SEO auditor. Score an article's on-page SEO and identify
specific improvements. Include E-E-A-T, social readiness, and people-first assessments.

Output JSON format:
{
  "score": 75,
  "checks": [
    {
      "category": "title|meta|headings|keywords|content|links|technical|eeat|social|structured_data",
      "status": "pass|fail|warning",
      "description": "what was checked",
      "details": "specific findings",
      "recommendation": "how to improve (if needed)"
    }
  ],
  "top_improvements": ["most important fixes"],
  "eeat_score": 0-100,
  "social_readiness": {
    "og_ready": true/false,
    "twitter_card_ready": true/false,
    "og_image_recommended": "description of recommended og:image"
  },
  "structured_data_recommendation": {
    "type": "Article|Recipe|HowTo|FAQPage|Review",
    "required_properties_missing": ["list of required schema properties not present"],
    "recommended_properties_missing": ["list of recommended schema properties to add"]
  },
  "people_first_score": 0-10
}

Standard SEO checks:
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
- Image alt text (if images mentioned)

E-E-A-T score (0-100) — assess these dimensions:
- Author credentials/expertise mentioned (20 pts): Does the content identify the author
  and their qualifications? Are credentials, experience, or track record evident?
- First-hand experience language (20 pts): Does the article use experience-based language
  like "In our experience", "We tested", "Based on working with..."?
- Source citations quality (20 pts): Are claims backed by authoritative, verifiable sources?
  Prefer .edu, .gov, peer-reviewed studies, official documentation, named experts.
- Transparency signals (20 pts): Is methodology explained? Are limitations acknowledged?
  Is it clear how conclusions were reached? Are conflicts of interest disclosed?
- Depth of analysis (20 pts): Does the content go beyond surface-level information?
  Are there unique insights, original data, or perspectives not found elsewhere?

Social readiness checks:
- og:title: Is the title compelling and suitable for social sharing? (under 60 chars ideal)
- og:description: Is there a meta description that works as social snippet? (under 200 chars)
- og:image: Recommend an image concept (1200px+ wide, 16:9 ratio, visually striking,
  relevant to topic, includes text overlay with key message if appropriate)
- Twitter card: Would the content display well as a Twitter/X summary_large_image card?
  Check title length, description, and image readiness.

People-first compliance score (0-10):
Evaluate against Google's helpful content questions:
- Serves existing audience, not just search engines
- Demonstrates first-hand expertise or deep knowledge
- Reader would feel they learned enough to achieve their goal
- Original content, not mass-produced or templated
- Adds genuine value beyond summarizing others
- Written by someone with clear expertise
- Leaves reader satisfied, not needing to search again
Deduct 1-2 points for each criterion not met.

Structured data recommendation:
- Determine the most appropriate schema type based on content:
  guide/general → Article, recipe → Recipe, tutorial → HowTo,
  FAQ-heavy → FAQPage, product review → Review
- List required properties for that schema type that are missing from the content
- List recommended (non-required) properties that would enhance rich results

Overall score calculation guidance:
- Standard SEO checks: ~40% weight
- E-E-A-T score: ~25% weight
- Social readiness: ~10% weight
- People-first compliance: ~15% weight
- Structured data readiness: ~10% weight"""


def seo_linter(article: dict) -> dict:
    """Lint article for on-page SEO.

    Args:
        article: Article dict with title, meta_description, content, faq, etc.
    """
    user_msg = f"""Audit this article for SEO:
{llm.format_json(article)}

Score and identify improvements across all dimensions:
standard SEO, E-E-A-T, social readiness, people-first compliance, and structured data."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
    return llm.parse_json_response(resp)
