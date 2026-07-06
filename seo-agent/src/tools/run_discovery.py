"""Discovery tool — interactive business intake conversation."""
from __future__ import annotations

from .. import llm


DISCOVERY_PROMPT = """You are conducting a business discovery interview for SEO strategy.
Ask ONE question at a time to gather the following information:

Required:
- Business description (what they do, who they serve)
- Primary goal (what success looks like)
- Competitors (3-5 URLs if known)

Optional but helpful:
- Locale/target market (country, language)
- Optimization mix (ai_citations, balanced, google_rankings)
- Notes (anything else relevant)

Rules:
- Ask ONE question at a time
- Be conversational but efficient
- If user gives partial info, ask for specifics
- When you have enough to start, summarize and ask "Ready to begin?"
- Return JSON when complete

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
    "locale": {"location_code": 2840, "location_label": "United States", "language_code": "en", "language_label": "English"},
    "competitors": [],
    "optimization_mix": "balanced",
    "notes": ""
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
