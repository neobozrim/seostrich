from __future__ import annotations

from .. import llm


SYSTEM_PROMPT = """You are a GEO (Generative Engine Optimization) analyst. Score how likely an article is to be cited by AI systems like ChatGPT, Perplexity, or Google AI Overview.

Output JSON format:
{
  "geo_score": 70,
  "citation_signals": [
    {
      "signal": "signal name",
      "strength": "strong|medium|weak",
      "evidence": "specific examples from article"
    }
  ],
  "improvements": ["how to increase AI citations"],
  "summary": "overall citability assessment"
}

Citation signals to evaluate:
- Factual, specific statements (statistics, data points)
- Authoritative source citations (.edu, .gov, industry reports)
- Clear, quotable sentences (standalone facts)
- Structured data presentation (tables, lists, definitions)
- Unique insights or original analysis
- Comprehensive topic coverage
- Clear entity relationships (who/what/when/where/why)
- Recent/timely information
- Expert perspective or credentials mentioned
- Actionable recommendations or conclusions"""


def geo_scorer(article: dict) -> dict:
    """Score article for AI citation potential."""
    user_msg = f"""Evaluate this article for AI citation potential:
{llm.format_json(article)}

Score GEO signals and suggest improvements."""

    resp = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3)
    return llm.parse_json_response(resp)
