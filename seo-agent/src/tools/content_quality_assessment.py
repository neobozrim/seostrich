from __future__ import annotations

from .. import llm


_SYSTEM_PROMPT = """You are an expert content quality evaluator trained in Google's E-E-A-T framework and helpful content guidelines.

Evaluate the given article against the following criteria and return JSON.

## E-E-A-T Scoring (0-10 each)
- **Experience**: Does the author share first-hand evidence, personal anecdotes, usage examples, or real-world testing?
- **Expertise**: Does the content demonstrate depth of knowledge, technical accuracy, and nuance that only a subject-matter expert could provide?
- **Authoritativeness**: Does the content cite authoritative sources, mention credentials, and offer unique insights not found elsewhere?
- **Trustworthiness**: Is the content transparent, balanced in perspective, well-sourced, and free of misleading claims?

## People-First Compliance (0-10)
Answer Google's helpful content questions:
1. Does the content serve an existing audience rather than just search engines?
2. Does it demonstrate first-hand expertise?
3. Is there a clear purpose for the page?
4. Will readers feel they learned enough to achieve their goal?
5. Would this content be useful if it appeared in a print magazine?

## Originality Score (0-10)
- Is the content offering a unique angle, not just rehashing common knowledge?
- Does it add value beyond what the top 10 search results already say?

## Comprehensiveness Score (0-10)
- Does it cover the topic fully?
- Does it anticipate and answer follow-up questions?

## Overall Quality (0-100)
Weighted score: E-E-A-T average (40%), People-First (20%), Originality (20%), Comprehensiveness (20%).

Output JSON format:
{
  "eeat_scores": {
    "experience": 0,
    "expertise": 0,
    "authoritativeness": 0,
    "trustworthiness": 0
  },
  "people_first_score": 0,
  "originality_score": 0,
  "comprehensiveness_score": 0,
  "overall_quality": 0,
  "strengths": ["list of strengths"],
  "weaknesses": ["list of weaknesses"],
  "improvements": ["specific actionable improvements"],
  "people_first_warnings": ["warnings about search-first content signals"]
}

Be strict and honest. Do not inflate scores. A score of 7+ means genuinely good."""


def content_quality_assessment(
    article: str, topic: str = "", author_info: str = ""
) -> dict:
    """Evaluate article quality against E-E-A-T and people-first criteria using LLM."""
    user_parts = ["Evaluate this article for content quality:"]

    if topic:
        user_parts.append(f"\nTopic: {topic}")

    if author_info:
        user_parts.append(f"\nAuthor information: {author_info}")

    user_parts.append(f"\n--- Article ---\n{article}\n--- End Article ---")
    user_parts.append("\nScore each criterion and provide specific, actionable feedback.")

    user_msg = "\n".join(user_parts)

    resp = llm.chat(user_msg, system=_SYSTEM_PROMPT, temperature=0.3)
    result = llm.parse_json_response(resp)

    # Compute overall_quality if not provided or as fallback
    if "overall_quality" not in result or result.get("overall_quality") == 0:
        eeat = result.get("eeat_scores", {})
        eeat_avg = sum([
            eeat.get("experience", 0),
            eeat.get("expertise", 0),
            eeat.get("authoritativeness", 0),
            eeat.get("trustworthiness", 0),
        ]) / 4
        people_first = result.get("people_first_score", 0)
        originality = result.get("originality_score", 0)
        comprehensiveness = result.get("comprehensiveness_score", 0)

        overall = (
            eeat_avg * 0.4
            + people_first * 0.2
            + originality * 0.2
            + comprehensiveness * 0.2
        ) * 10
        result["overall_quality"] = round(overall)

    return result
