"""Post-response memory synthesis with self-critique.

Two-pass approach (inspired by keyword clustering):
1. Synthesis: Extract candidate memories
2. Critique: Review for quality, duplicates, and correctness

Analyzes completed sessions to extract new facts, learnings, and decisions
that should be recorded for future sessions.
"""
import json
from typing import Any
from .. import memory
from ..llm import chat


def synthesize_memories_from_session(
    session_id: str,
    messages: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    agent: str = "seo-agent"
) -> dict[str, Any]:
    """
    Analyze a completed session and extract memories to record.

    Two-pass approach:
    1. Synthesis: Extract candidate memories
    2. Critique: Review for quality, duplicates, and correctness

    Args:
        session_id: Session identifier
        messages: List of messages from the session
        tool_results: List of tool execution results
        agent: Which agent to attribute memories to ("seo-agent", "orchestrator", etc.)

    Returns:
        Dict with status and counts of extracted memories
    """
    # Build conversation summary
    user_messages = [m["content"] for m in messages if m.get("role") == "user"]
    assistant_messages = [m["content"] for m in messages if m.get("role") == "assistant" and m.get("content")]

    if not user_messages:
        return {"status": "skipped", "reason": "No user messages"}

    # Prepare LLM prompt
    conversation_summary = "\n".join([
        f"User request: {user_messages[0][:500]}",
        f"Assistant response: {assistant_messages[-1][:500] if assistant_messages else 'No response'}",
        f"Tools used: {', '.join(set(t.get('tool', '?') for t in tool_results))}",
        f"Total tool calls: {len(tool_results)}"
    ])

    # ── Pass 1: Synthesis ──────────────────────────────────────────
    synthesis_prompt = f"""Analyze this SEO agent session and extract ONLY high-quality, stable memories for the blackboard.

SESSION:
{conversation_summary}

CRITICAL QUALITY GATES:

**FACTS** - Only extract if ALL of these are true:
✓ About user's business, technical setup, constraints, or preferences (STABLE across sessions)
✗ NOT implementation details (tool counts, file names, code changes) - these change frequently
✗ NOT session-specific results (audit findings, keyword counts) - these belong in run-summaries
✓ Would be useful across MULTIPLE future sessions

Good facts: "User's blog runs on Astro framework", "productpirates.club targets CEE product managers", "User prefers concise technical recommendations"
BAD facts: "SEO agent has 31 tools", "docs/TOOLS.md created", "Keyword research returned 50 keywords"

**LEARNINGS** - Only extract if:
✓ Represents a pattern, rule, or insight discovered through experience
✓ Would change how future sessions are conducted
✗ NOT obvious or trivial

Good learnings: "Meta descriptions under 155 chars get higher CTR", "User prefers actionable recommendations over lengthy explanations"

**DECISIONS** - Only extract if:
✓ Represents a significant choice with clear reasoning
✓ Would inform future decisions
✗ NOT routine tool usage

Good decisions: "Chose long-tail keywords over broad terms because site has low authority (reason)"

Return JSON with arrays for each category. If nothing meets the quality bar, return empty arrays [].

{{
  "facts": ["fact 1", "fact 2"],
  "learnings": ["learning 1"],
  "decisions": ["decision 1 (reason)"]
}}

Be SELECTIVE. Quality over quantity. Empty arrays are preferred over low-quality entries."""

    try:
        response = chat(synthesis_prompt, system="You are a memory extraction specialist for an SEO agent. Extract only meaningful, non-obvious memories that would help future sessions.")

        # Parse JSON response
        synthesis_result = json.loads(response.get("content", ""))

        # ── Pass 2: Self-Critique ──────────────────────────────────
        critique_prompt = f"""Review the extracted memories for quality, correctness, and duplicates.

ORIGINAL SESSION:
{conversation_summary}

EXTRACTED MEMORIES:
```json
{json.dumps(synthesis_result, indent=2)}
```

Apply these 5 checks:

1. **Stability**: Are facts actually stable? (not implementation details or session-specific)
2. **Usefulness**: Would these memories help future sessions?
3. **Cross-type duplicates**: Is a "fact" actually a learning? Is a "decision" actually a fact?
4. **Redundancy**: Do any memories say the same thing in different words?
5. **Format**: Do decisions include reasoning? Are entries concise?

Return JSON:
{{
  "verdict": "ok" | "corrected",
  "notes": "brief explanation if corrections made",
  "facts": ["corrected facts if needed"],
  "learnings": ["corrected learnings if needed"],
  "decisions": ["corrected decisions if needed"]
}}

If verdict is "ok", include the original arrays. If "corrected", include the improved versions."""

        critique_response = chat(critique_prompt, system="You are a memory quality reviewer. Be strict about quality standards.")

        critique_result = json.loads(critique_response.get("content", ""))

        # Use corrected version if provided
        if critique_result.get("verdict", "").lower() == "corrected":
            final_memories = {
                "facts": critique_result.get("facts", []),
                "learnings": critique_result.get("learnings", []),
                "decisions": critique_result.get("decisions", [])
            }
        else:
            final_memories = synthesis_result

        facts = final_memories.get("facts", [])
        learnings = final_memories.get("learnings", [])
        decisions = final_memories.get("decisions", [])

        # Deduplication: check against existing memories
        existing_facts = memory.read_facts().lower()
        existing_learnings = memory.read_learnings().lower()
        existing_decisions = memory.read_decisions().lower()

        def is_duplicate(new_item: str, existing_content: str) -> bool:
            """Check if new item is substantially similar to existing content."""
            new_lower = new_item.lower()
            # Simple check: if 80% of words overlap, consider it duplicate
            new_words = set(new_lower.split())
            existing_words = set(existing_content.split())
            if not new_words:
                return True
            overlap = len(new_words & existing_words) / len(new_words)
            return overlap > 0.8

        # Filter out duplicates
        facts = [f for f in facts if not is_duplicate(f, existing_facts)]
        learnings = [l for l in learnings if not is_duplicate(l, existing_learnings)]
        decisions = [d for d in decisions if not is_duplicate(d, existing_decisions)]

        # Record to memory
        for fact in facts:
            memory.record_fact(fact, agent=agent)

        for learning in learnings:
            memory.record_learning(learning, agent=agent)

        for decision in decisions:
            memory.record_decision(decision, agent=agent)

        return {
            "status": "success",
            "facts_count": len(facts),
            "learnings_count": len(learnings),
            "decisions_count": len(decisions),
            "critique_verdict": critique_result.get("verdict", "unknown"),
        }

    except json.JSONDecodeError as e:
        return {"status": "error", "reason": f"Failed to parse LLM response: {e}"}
    except Exception as e:
        return {"status": "error", "reason": f"Memory synthesis failed: {e}"}
