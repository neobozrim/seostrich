---
name: self-learning-loop
description: Post-run self-improvement analysis — reads traces from Braintrust, identifies patterns, proposes improvements with LLM-based deduplication
applies_to: [seo-agent, orchestrator, branding]
source: auto-skill
updated_at: '2026-07-09T00:00:00.000Z'
---

# Self-Learning Loop

After every agent run, this skill triggers to analyze the session and propose improvements.

## When to Run

The self-learning loop runs automatically after each successful agent run in the orchestrator. It analyzes:
- The conversation transcript (from Braintrust trace)
- Tool calls and their outcomes
- Memory state before and after the run

## What It Does

### 1. Trace Analysis

Reads the run transcript from Braintrust and identifies:
- **Goal achieved?** Did the agent accomplish what the user asked?
- **Tool effectiveness:** Which tools worked, which failed, which were unused?
- **Memory usage:** Did the agent read and write memory appropriately?
- **Conversation flow:** Was the user satisfied, did they repeat requests, did they correct the agent?

### 2. Improvement Proposals

Uses an LLM to analyze the session and generate specific, actionable proposals:

**For recurring tool failures:**
- Proposal: "Fix DataForSEO timeout handling" or "Add retry logic to keyword_research"
- Rationale: "Tool failed 3 times in last 5 runs due to timeout"
- Implementation: Specific code change or configuration update

**For missed opportunities:**
- Proposal: "Record user's business goals as facts"
- Rationale: "User mentioned their goal is X, but this wasn't recorded in facts.md"
- Implementation: Update system prompt or add explicit memory recording step

**For inefficient patterns:**
- Proposal: "Read memory before planning"
- Rationale: "Agent planned from scratch, but memory already contained relevant context"
- Implementation: Add memory read step to agent workflow

**For quality issues:**
- Proposal: "Stop recording 'Run X used tools Y' as facts"
- Rationale: "This is run metadata, not a fact about the world"
- Implementation: Update quality gate in memory-recording skill

### 3. Deduplication

Before storing proposals, the system uses LLM judgment to check if the new proposal duplicates an existing pending proposal. This prevents accumulation of redundant proposals addressing the same issue.

### 4. Missing Memory Detection

The system also identifies facts/learnings/decisions that should have been recorded but weren't. Before adding them, it uses LLM judgment to check if the proposed memory is semantically similar to existing entries (not just word overlap).

Missing memories that pass the dedup check are automatically added with the `[from-improvement-loop]` tag.

### 5. Storage

Proposals are stored in `agent-memory/improvements/proposal-YYYYMMDD_HHMMSS.md` with:
- Summary of the run
- Identified issues
- Proposed improvements
- Rationale for each proposal
- Implementation steps

### 6. User Review

Proposals are shown to the user (via admin panel or chat) for review. The user can:
- **Apply** — Implement the improvement immediately
- **Defer** — Keep the proposal for later consideration
- **Dismiss** — Delete the proposal

## How It Works

### Trigger

After `run_orchestrator_stream()` completes successfully, if the run had ≥1 tool call:

```python
if session_data["agent_calls"]:
    self_learning_loop.run(session_id, session_data)
```

### Analysis Process

1. **Fetch trace** from Braintrust (with disk caching and retry logic)
   - Session ID, user request, messages, tool calls, outcomes
   - Metadata: tools used, success/failure counts, duration

2. **Load memory state**
   - Current facts, learnings, decisions
   - Recent run summaries for context

3. **Analyze transcript**
   - Parse user messages for satisfaction signals
   - Parse tool calls for success/failure patterns
   - Parse agent responses for quality indicators

4. **Generate proposals**
   - Use LLM to synthesize findings into proposals
   - Each proposal has: issue, rationale, implementation
   - Prioritize by impact and effort

5. **Deduplicate**
   - Check new proposals against existing pending proposals using LLM judgment
   - Filter out duplicates

6. **Store and notify**
   - Write proposal to file
   - Apply missing memories immediately (with tag)
   - Notify user via chat or admin panel

## Integration with Memory System

The self-learning loop respects the memory-recording skill:
- Proposes improvements to memory quality (not just adding more memories)
- Identifies when the agent violated memory protocols (garbage facts, missing rationale)
- Suggests superseding outdated facts/learnings/decisions
- Uses LLM judgment for deduplication instead of simple word overlap

## Integration with Braintrust

The self-learning loop uses Braintrust traces with:
- **Retry logic:** Exponential backoff on 429 rate limit errors
- **Disk caching:** Traces cached for 1 hour to avoid repeated API calls
- **Session extraction:** Matches session_id in event metadata or input

This creates a feedback loop: the self-learning loop improves the agent, and Braintrust tracks whether the improvements actually work.
