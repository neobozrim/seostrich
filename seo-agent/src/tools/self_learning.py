"""Self-learning loop for continuous improvement."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from .. import memory
from ..tools.braintrust import read_braintrust_trace


def run_self_learning(session_id: str, agent: str = "seo-agent") -> Dict[str, Any]:
    """
    Run self-learning analysis after an agent run.

    Args:
        session_id: The session to analyze
        agent: Which agent to attribute memories to ("seo-agent", "orchestrator", etc.)

    Returns:
        Dict with status and improvement count
    """
    print(f"[Self-Learning] Analyzing session {session_id}...")

    # Read trace FROM Braintrust
    session_data = read_braintrust_trace(session_id)
    if not session_data:
        print(f"[Self-Learning] No Braintrust trace found for session {session_id}")
        return {"status": "error", "message": f"No Braintrust trace found for session {session_id}"}

    print(f"[Self-Learning] [OK] Found trace in Braintrust (messages={len(session_data.get('messages', []))}, tools={len(session_data.get('tool_results', []))})")

    # Read current memories
    memories = memory.read_all()

    # Analyze and generate improvements
    improvements = _generate_improvements(session_data, memories)

    # Identify missing memories
    missing = _identify_missing_memories(session_data, memories)

    # Store proposals (only non-empty ones, batched into one file)
    proposals_stored = _store_proposals(improvements, missing)

    # Apply missing memories immediately (with tag)
    if missing:
        _apply_missing_memories(missing, agent)

    return {
        "status": "success",
        "improvements_proposed": len(improvements),
        "missing_memories_added": len(missing),
        "proposals_stored": proposals_stored
    }


def run_self_learning_on_demand() -> Dict[str, Any]:
    """
    Run self-learning on recent traces (last 5 sessions).

    Returns:
        Dict with status and counts
    """
    print("[Self-Learning] Analyzing recent sessions...")

    # Get recent session IDs from Braintrust
    from ..tools.braintrust import list_recent_sessions
    recent_sessions = list_recent_sessions(limit=5)

    total_improvements = 0
    total_missing = 0

    for session_id in recent_sessions:
        result = run_self_learning(session_id)
        if result["status"] == "success":
            total_improvements += result["improvements_proposed"]
            total_missing += result["missing_memories_added"]

    return {
        "status": "success",
        "sessions_analyzed": len(recent_sessions),
        "total_improvements": total_improvements,
        "total_missing_added": total_missing
    }


def _normalize_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM output keys to snake_case.

    LLMs often return keys like 'Current State' or 'Proposed Change'
    instead of 'current_state' / 'proposed_change'.
    """
    if not isinstance(obj, dict):
        return obj

    mapping = {
        'current state': 'current_state',
        'proposed change': 'proposed_change',
        'category': 'category',
        'topic': 'topic',
        'rationale': 'rationale',
        'implementation': 'implementation',
        'priority': 'priority',
        'content': 'content',
    }

    normalized = {}
    for key, value in obj.items():
        lower_key = key.strip().lower()
        normalized_key = mapping.get(lower_key, lower_key.replace(' ', '_'))
        normalized[normalized_key] = value

    return normalized


def _is_meaningful(imp: Dict[str, Any]) -> bool:
    """Check if an improvement has actual content (not all N/A)."""
    required_fields = ['current_state', 'proposed_change', 'rationale']
    for field in required_fields:
        value = imp.get(field, '')
        if value and value.strip() and value.strip().lower() not in ('n/a', 'none', ''):
            return True
    # Also check if topic has content
    topic = imp.get('topic', '')
    if topic and topic.strip() and topic.strip().lower() not in ('untitled', 'n/a', 'none', ''):
        return True
    return False


def _generate_improvements(
    session_data: Dict[str, Any],
    memories: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    """Generate improvement proposals from session analysis."""
    from ..llm import chat, extract_json

    # Extract key info from session
    messages = session_data.get('messages', [])
    tool_results = session_data.get('tool_results', [])

    # Get user message from first message
    user_message = ""
    for msg in messages:
        if msg.get('role') == 'user':
            user_message = msg.get('content', '')
            break

    # Prepare context
    context = f"""
## Session Summary
Session ID: {session_data.get('session_id')}
User Message: {user_message[:200]}
Tool Calls: {len(tool_results)}
Messages: {len(messages)}

## Current Memories (shared blackboard)
Facts: {len(memories.get('facts', []))}
Learnings: {len(memories.get('learnings', []))}
Decisions: {len(memories.get('decisions', []))}

## Tool Usage
{json.dumps([{'tool': tr.get('tool'), 'args': tr.get('args')} for tr in tool_results], indent=2, default=str)}
"""

    prompt = f"""You are analyzing an AI agent's performance to propose specific improvements.

{context}

Based on this session and the current memory state, identify GENUINE problems that need fixing. 

CRITICAL: Only propose improvements if you identify real issues. Common session patterns (successful audits, normal tool usage, expected workflows) do NOT need improvement proposals. 

Propose improvements ONLY when you see:
- Repeated failures or errors that suggest a systemic issue
- Tool calls that clearly didn't achieve the user's goal
- Missing capabilities that prevented the agent from helping
- Inefficiencies that waste significant time/tokens
- Prompt confusion causing the agent to misinterpret requests

Do NOT propose:
- Feature expansions (adding more parameters, new tools)
- Over-engineering (pipelines, orchestrators) for simple working flows
- Optimizations for already-working patterns
- Memory management if the system already has memory caps

If the session went smoothly and you see no genuine issues, output an empty array: []

For each genuine improvement (0-4), output a JSON object with EXACTLY these keys:
- category: one of "tool_design", "prompt_engineering", "memory_usage", "workflow"
- topic: short title (under 60 chars)
- current_state: what is happening now (specific problem)
- proposed_change: what should change (specific fix)
- rationale: why this matters
- implementation: concrete steps to implement
- priority: "high", "medium", or "low"

IMPORTANT: Use snake_case keys exactly as listed above.

Output ONLY a JSON array of improvement objects (or [] if no issues). No other text."""

    response = chat(
        prompt,
        system="You are an AI agent performance analyst. Output valid JSON only.",
        temperature=0.3
    )

    try:
        improvements = extract_json(response.get("content", ""))
        if not isinstance(improvements, list):
            improvements = [improvements]

        # Normalize keys and filter to meaningful ones
        result = []
        for imp in improvements:
            normalized = _normalize_keys(imp)
            if _is_meaningful(normalized):
                result.append(normalized)

        return result
    except (json.JSONDecodeError, ValueError):
        print("[Self-Learning] Failed to parse improvement proposals")
        return []


def _identify_missing_memories(
    session_data: Dict[str, Any],
    current_memories: Dict[str, List[str]]
) -> List[Dict[str, str]]:
    """Identify facts/learnings/decisions that should have been recorded but weren't."""
    from ..llm import chat, extract_json

    # Combine all current memories for context
    all_memories = []
    for category, entries in current_memories.items():
        all_memories.extend(entries)

    # Extract session details
    messages = session_data.get('messages', [])
    tool_results = session_data.get('tool_results', [])

    context = f"""
## Session
Messages: {json.dumps(messages, indent=2, default=str)}
Tool Calls: {json.dumps(tool_results, indent=2, default=str)}

## Current Memories
{json.dumps(all_memories, indent=2)}
"""

    prompt = f"""You are reviewing an AI agent's conversation to identify GENUINELY NEW information that should be recorded in memory.

{context}

CRITICAL: The agent already ran memory synthesis after this session and may have already recorded key facts/learnings. Your job is to find what was MISSED, not to re-record everything.

Check each proposed memory against the Current Memories above. If it's already captured (even with different wording), DO NOT add it again.

Add memories ONLY when you find:
- Truly new facts not already in the memory (different domain, new technical detail, new constraint)
- Learnings that represent a genuinely new pattern or insight not yet recorded
- Decisions that weren't already documented

Do NOT add:
- Information that's a rephrasing of existing memories
- Session-specific details (timestamps, session IDs, tool call counts)
- Obvious facts (the agent exists, tools work, etc.)
- Tool outputs or audit results (those belong in the session, not long-term memory)

If everything important is already captured, output an empty array: []

For each genuinely missing memory (0-3), output a JSON object with EXACTLY these keys:
- category: "facts", "learnings", or "decisions"
- content: the memory text (concise and specific, under 100 chars)
- rationale: why this should be remembered and isn't already captured

IMPORTANT: Use snake_case keys exactly as listed.

Output ONLY a JSON array (or [] if nothing new). No other text."""

    response = chat(
        prompt,
        system="You are an AI memory curator. Output valid JSON only.",
        temperature=0.2
    )

    try:
        missing = extract_json(response.get("content", ""))
        if not isinstance(missing, list):
            missing = [missing]

        # Normalize keys
        return [_normalize_keys(m) for m in missing]
    except (json.JSONDecodeError, ValueError):
        print("[Self-Learning] Failed to parse missing memories")
        return []


def _store_proposals(
    improvements: List[Dict[str, Any]],
    missing_memories: List[Dict[str, str]],
) -> int:
    """Store improvement proposals in the blackboard memory improvements folder.

    All proposals for a session are batched into a single file.
    Empty proposals are skipped.
    Uses LLM judgment to check for duplicate proposals against existing pending ones."""
    # Use the shared memory path: agent-memory/improvements/
    improvements_dir = memory._get_memory_dir() / "improvements"
    improvements_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not improvements and not missing_memories:
        return 0

    # Deduplicate proposals against existing pending ones using LLM judgment
    if improvements:
        improvements = _dedup_proposals(improvements, improvements_dir)
    
    if not improvements and not missing_memories:
        return 0

    # Build a single batched proposal file
    filename = f"proposal-{timestamp}.md"
    filepath = improvements_dir / filename

    content = f"""# Improvement Proposals — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

**Session analyzed:** {len(improvements)} improvements, {len(missing_memories)} missing memories
**Status:** pending

"""

    # Add improvement proposals
    if improvements:
        content += "## Improvements\n\n"
        for i, imp in enumerate(improvements, 1):
            content += f"""### {i}. {imp.get('topic', 'Untitled')}

**Category:** {imp.get('category', 'N/A')}
**Priority:** {imp.get('priority', 'medium')}

**Current:** {imp.get('current_state', 'N/A')}
**Proposed:** {imp.get('proposed_change', 'N/A')}
**Why:** {imp.get('rationale', 'N/A')}
**How:** {imp.get('implementation', 'N/A')}

"""

    # Add missing memories section
    if missing_memories:
        content += "## Missing Memories (auto-applied with [from-improvement-loop] tag)\n\n"
        for mem in missing_memories:
            content += f"- **{mem.get('category', 'unknown').title()}:** {mem.get('content', 'N/A')}\n"
            rationale = mem.get('rationale', '')
            if rationale:
                content += f"  - _{rationale}_\n"
        content += "\n"

    filepath.write_text(content)
    return 1


def _dedup_proposals(
    new_improvements: List[Dict[str, Any]],
    improvements_dir: Path
) -> List[Dict[str, Any]]:
    """Deduplicate proposals against existing pending proposals using LLM judgment.

    Args:
        new_improvements: List of proposed improvements from this session
        improvements_dir: Directory containing existing proposal files

    Returns:
        Filtered list of improvements (duplicates removed)
    """
    from ..llm import chat
    
    # Load existing pending proposals
    existing_proposals = []
    for prop_file in improvements_dir.glob("proposal-*.md"):
        try:
            content = prop_file.read_text(encoding="utf-8", errors="replace")
            if "**Status:** pending" in content:
                # Extract proposal titles/topics
                import re
                titles = re.findall(r"### \d+\. (.+)", content)
                existing_proposals.extend(titles)
        except OSError:
            continue
    
    if not existing_proposals:
        # No existing proposals, return all new ones
        return new_improvements
    
    # Use LLM to check each new proposal against existing ones
    existing_summary = "\n".join(f"- {title}" for title in existing_proposals[:20])
    
    deduped = []
    for imp in new_improvements:
        topic = imp.get('topic', 'Untitled')
        proposed_change = imp.get('proposed_change', '')
        
        dedup_prompt = f"""Is this new proposal essentially the same as any existing proposal?

New proposal: "{topic}" — {proposed_change[:150]}

Existing pending proposals:
{existing_summary}

Answer ONLY "yes" if the new proposal addresses the same issue as an existing one, or "no" if it's genuinely different."""
        
        try:
            response = chat(
                dedup_prompt,
                system="You are a proposal deduplication judge. Answer only 'yes' or 'no'.",
                temperature=0.0,
                max_tokens=10
            )
            answer = response.get("content", "").strip().lower()
            if "yes" not in answer:
                deduped.append(imp)
        except Exception:
            # If LLM check fails, keep it (better to have a duplicate than miss a proposal)
            deduped.append(imp)
    
    return deduped


def _apply_missing_memories(
    missing_memories: List[Dict[str, str]],
    agent: str = "seo-agent"
) -> None:
    """Apply missing memories to the appropriate memory files with tag.

    Uses LLM judgment to check for semantic duplicates instead of word overlap."""
    if not missing_memories:
        return

    # Load existing memories for deduplication
    existing = {
        "facts": memory.read_facts(),
        "learnings": memory.read_learnings(),
        "decisions": memory.read_decisions(),
    }
    
    # Filter missing memories through LLM dedup check
    from ..llm import chat, extract_json
    
    to_add = []
    for mem in missing_memories:
        category = mem.get('category', '').lower()
        content = mem.get('content', '')
        
        if not content:
            continue
        
        category_existing = existing.get(category, '')
        if not category_existing.strip():
            # No existing entries in this category, add it
            to_add.append(mem)
            continue
        
        # Use LLM to check if this is semantically similar to existing entries
        dedup_prompt = f"""Is the proposed memory entry semantically equivalent or substantially similar to any existing entry?

Proposed: "{content}"

Existing entries in {category}:
{category_existing[:1500]}

Answer ONLY "yes" if the proposed entry says the same thing (in different words) as an existing entry, or "no" if it contains genuinely new information."""
        
        try:
            response = chat(
                dedup_prompt,
                system="You are a memory deduplication judge. Answer only 'yes' or 'no'.",
                temperature=0.0,
                max_tokens=10
            )
            answer = response.get("content", "").strip().lower()
            if "yes" not in answer:
                to_add.append(mem)
        except Exception:
            # If LLM check fails, add it (better to add a duplicate than miss a memory)
            to_add.append(mem)

    added = 0
    skipped = len(missing_memories) - len(to_add)

    for mem in to_add:
        category = mem.get('category', '').lower()
        content = mem.get('content', '')
        tagged_content = f"{content} [from-improvement-loop]"

        if category == 'facts':
            memory.record_fact(tagged_content, agent=agent)
            added += 1
        elif category == 'learnings':
            memory.record_learning(tagged_content, agent=agent)
            added += 1
        elif category == 'decisions':
            memory.record_decision(tagged_content, agent=agent)
            added += 1
        else:
            skipped += 1

    if added:
        print(f"[Self-Learning] Added {added} memories (skipped {skipped} duplicates)")
    elif skipped:
        print(f"[Self-Learning] No new memories added ({skipped} skipped as duplicates)")
    else:
        print("[Self-Learning] No memories to add")
