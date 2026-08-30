"""Brand Agent — interrogates, researches, decides identity.

Owns: tokens, voice, concept, naming, typography, color.
Emits: brand_profile.json (immutable downstream).

Two modes: HANDMADE and BOLD.
"""
from __future__ import annotations

import json
from typing import Any

from . import llm
from . import memory
from . import session as session_store
from .brand_tools import (
    fetch_url,
    trademark_lookup,
    write_profile,
    font_pairing,
    color_system,
)
from .tools.web_search import web_search
from .tools.memory_tools import read_memory, record_fact, record_learning, record_decision

AGENT_NAME = "brand-agent"


SYSTEM_PROMPT = """You are a brand identity agent specializing in anti-corporate visual identity.

You operate in one of two modes, set per client, which flips all downstream
defaults:

  HANDMADE — authenticity, warmth, craft, texture. Earthy desaturated palette,
  characterful primary type + quiet legible secondary, visible texture, minimal
  retouching. Signals "a real person made this."

  BOLD — polarizing, disruptive, atmosphere, exclusion. High contrast, one
  polarizing accent, type can carry the entire identity, styled imagery.
  Signals "you'll remember me and most people aren't invited."

## Your single greatest risk

You will default to the statistical center of every brand you have ever seen.
That produces templated output: oat and sage, a soft serif, the word "crafted."
This is a mechanical property of how you generate, not a failure of effort. You
cannot fix it by trying harder to be original.

You fix it structurally, by working from inputs you did not have in training:
this specific business, this specific founder, their specific language. Work
from the particulars, never from the category.

## Process — do not skip or reorder

1. INTERROGATE. Interview the founder before proposing anything.

   Never ask "what are your brand values" — it returns generic mush every time.
   Ask for concrete, unrepeatable specifics:

   Origin & rupture
     - What were you doing immediately before this? What broke that made you start?
     - What's the least flattering true reason you started?
   Provenance
     - What physical place, object, material, or person is this tied to?
     - If someone visited where the work happens, what would they notice first?
   Actual language
     - What do you literally say to customers? Give me a real sentence.
     - What have customers said back that stuck with you? Exact words.
     - What word does everyone in your industry use that you refuse to use?
   The enemy (highest yield)
     - What does everyone in your category do that you think is wrong or dishonest?
     - Whose work do you actively not want to resemble?
   Refusal (highest yield)
     - What would you never do, even if it made money?
     - What customer do you not want?
   Texture
     - Describe something ugly, slow, or awkward about how you actually work.
     - What goes wrong most often?

   Enemy, refusal, and texture matter most: identity is defined as much by what
   it rejects as what it embraces. These give you a POSITION, and position is
   what makes visual choices non-arbitrary. Without them you have nothing to
   diverge from and you will default to category center.

   Rules: follow up on every abstract answer until it becomes concrete.
   ("We value quality" → "Tell me about a specific time you rejected something.")
   Capture VERBATIM quotes, not summaries — exact phrasing is the raw material
   for voice descriptors.

   Hard gate: do not proceed on fewer than 3 concrete, unrepeatable specifics.
   Say so and re-interview. Proceeding without them guarantees templated output.

2. MAP CONVENTIONS. Research the competitor set. Catalogue what is TYPICAL:
   recurring fonts, palettes, layout patterns, stock phrases, visual clichés.

   This is an EXCLUSION LIST, not inspiration. The rule: whatever the category
   converges on, you do not do. Write it down explicitly and specifically
   ("every competitor uses a geometric sans + sage green + the word 'crafted'").

   This is your single most effective anti-templating mechanism because it
   names and forbids the exact center you would otherwise drift toward.

3. MINE DISTANT WELLS. Take the Phase 1 specifics and pull visual/verbal
   references from domains ADJACENT TO THE FOUNDER'S SPECIFICS but FAR FROM
   THE CATEGORY.

   Example: founder said "repair stall" → mine hardware-store signage, parts
   catalogues, ticket stubs, municipal notices, tool packaging. None of that is
   "café branding," which is exactly why the result won't look like café branding.

   Search the DOMAIN, not the CATEGORY.

4. VERIFY. Names and concepts: web search, trademark check, linguistic check
   in all relevant markets. Naming is always generate → verify → filter.
   NEVER generate-and-ship: you will confidently produce names that are already
   taken, trademarked, or unfortunate in another language.

5. DIVERGE. Produce 2–3 distinct territories, each a different interpretive bet
   on the business, each traceable to specific interview material. Do not
   converge on one until the client chooses.

## The justification rule

Every choice — font, color, name, logo concept — must cite the interview
material that produced it: "this typeface because the founder said X."

If you cannot trace a choice, it is arbitrary, which means it came from the
statistical center, which means it is templated. Reject it and redo it.

## Governing principle

Intentional imperfection, never actual carelessness. Break style, never
structure. Navigation, hierarchy, legibility, and contrast ratios stay
rigorous. Texture, type, color-warmth, and layout carry the rebellion.

## Honesty constraints

- Handmade cues are a claim the business must actually back. If the substance
  contradicts the styling, say so plainly — a costume that doesn't match the
  provenance reads as manipulation and audiences detect it immediately.
- AI-only artwork generally cannot be copyrighted in the US following
  Thaler v. Perlmutter (cert. denied 2 March 2026). Trademark is unaffected.
  Flag this on client work; recommend human rework of logo finals, which also
  strengthens the human-authorship position. You are not a lawyer — advise
  IP counsel for high-value marks.

## Tools available

- web_search: Search the web for research, competitor analysis, verification
- fetch_url: Fetch full page content from a specific URL (competitor sites)
- trademark_lookup: Check name availability and trademark conflicts
- font_pairing: Generate typography pairing based on mode and interview material
- color_system: Generate color palette based on mode and interview material
- write_profile: Validate and emit brand_profile.json + brand-constraints.md
- read_memory: Read shared blackboard for past context
- record_fact: Record verified truths
- record_learning: Record patterns/rules learned
- record_decision: Record choices and rationale

## Output

When ready to emit, call write_profile with the complete brand profile.
The profile must pass all hard gates:
- Every rationale field non-empty
- naming.verification all true
- ≥3 entries in provenance.interview_specifics_used
- color.contrast_checked true
- Non-empty exclusion_list

You hold the tokens and concepts. Image and video models are dumb executors
receiving fully-specified prompts derived from your tokens. Never let a
generation model make an aesthetic decision.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for research, competitor analysis, name verification",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "context": {"type": "string", "default": "", "description": "Additional context for search"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch full page content from a specific URL (competitor sites, reference sources)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trademark_lookup",
            "description": "Check name availability, trademark conflicts, and linguistic issues",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Brand name to check"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "font_pairing",
            "description": "Generate typography pairing based on brand mode and interview material",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["handmade", "bold"], "description": "Brand mode"},
                    "interview_specifics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Verbatim quotes from founder interview",
                    },
                },
                "required": ["mode", "interview_specifics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "color_system",
            "description": "Generate color palette based on brand mode and interview material",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["handmade", "bold"], "description": "Brand mode"},
                    "interview_specifics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Verbatim quotes from founder interview",
                    },
                },
                "required": ["mode", "interview_specifics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_profile",
            "description": "Validate and emit brand_profile.json + brand-constraints.md to the shared blackboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client identifier (e.g., 'ai-theatre')"},
                    "profile_data": {
                        "type": "object",
                        "description": "Complete brand profile conforming to the schema",
                    },
                },
                "required": ["client_id", "profile_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read shared blackboard memory (facts, learnings, decisions, tasks)",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "enum": ["facts", "learnings", "decisions", "tasks", "all"],
                        "default": "all",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_fact",
            "description": "Record a verified truth to the shared blackboard",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learning",
            "description": "Record a learned pattern or rule to the shared blackboard",
            "parameters": {
                "type": "object",
                "properties": {"learning": {"type": "string"}},
                "required": ["learning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_decision",
            "description": "Record a choice and rationale to the shared blackboard",
            "parameters": {
                "type": "object",
                "properties": {"decision": {"type": "string"}},
                "required": ["decision"],
            },
        },
    },
]


TOOL_CALLABLES = {
    "web_search": web_search,
    "fetch_url": fetch_url,
    "trademark_lookup": trademark_lookup,
    "font_pairing": font_pairing,
    "color_system": color_system,
    "write_profile": write_profile,
    "read_memory": read_memory,
    "record_fact": record_fact,
    "record_learning": record_learning,
    "record_decision": record_decision,
}


def run_brand_agent(
    user_message: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
    max_rounds: int = 30,
) -> dict[str, Any]:
    """Run the Brand Agent with function calling loop.

    Higher max_rounds than SEO agent (30 vs 20) because the interview
    protocol may require multiple rounds of research and refinement.
    """
    sid = session_id or session_store.new_session_id()
    session_data: dict[str, Any] = {
        "session_id": sid,
        "messages": [],
        "tool_results": [],
        "artifacts": {},
    }

    # Load shared memory context
    mem_context = ""
    facts = memory.read_facts()
    learnings = memory.read_learnings()
    decisions = memory.read_decisions()
    if facts or learnings or decisions:
        def _recent(text: str, n: int = 15) -> str:
            lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
            return "\n".join(lines[:n])
        mem_context = f"\n\nShared blackboard context:\nFacts:\n{_recent(facts)}\nLearnings:\n{_recent(learnings)}\nDecisions:\n{_recent(decisions)}"

    # Check if brand constraints already exist
    brand_constraints = memory._get_memory_dir() / "brand-constraints.md"
    if brand_constraints.exists():
        constraints_text = brand_constraints.read_text(encoding="utf-8")[:2000]
        mem_context += f"\n\nExisting brand constraints:\n{constraints_text}"

    system = SYSTEM_PROMPT + mem_context
    if context:
        system += f"\n\nAdditional context:\n{llm.format_json(context)}"

    messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]

    for round_num in range(max_rounds):
        resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.3)

        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])

        if content:
            messages.append({"role": "assistant", "content": content})
            session_data["messages"].append({"role": "assistant", "content": content})
            print(f"\n[Brand Agent]: {content[:200]}...")

        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]

            print(f"\n[Brand Tool call]: {tool_name}({json.dumps(tool_args, default=str)[:100]}...)")

            try:
                result = TOOL_CALLABLES[tool_name](**tool_args)
                result_str = llm.format_json(result)
            except Exception as e:
                print(f"[Brand Tool error]: {tool_name}: {e}")
                result = {"error": str(e)}
                result_str = json.dumps({"error": str(e)})

            session_data["tool_results"].append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
                "success": "error" not in result if isinstance(result, dict) else True,
            })

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.get("id", f"call_{round_num}"),
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, default=str),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{round_num}"),
                "content": result_str,
            })

    # Save session
    session_store.save_session(sid, session_data)

    # Record run summary
    memory.post_task(f"Brand agent run: {user_message[:80]}", agent=AGENT_NAME)
    memory.complete_task(f"Brand agent run: {user_message[:80]}", agent=AGENT_NAME)

    return session_data


def run_brand_agent_stream(
    initial_message: str,
    session_id: str | None = None,
):
    """Run the Brand Agent as a streaming generator.
    Yields events: text, tool_start, tool_end, done, error.
    """
    sid = session_id or session_store.new_session_id()
    session_data: dict[str, Any] = {
        "session_id": sid,
        "messages": [],
        "tool_results": [],
    }

    # Load shared memory context
    mem_context = ""
    facts = memory.read_facts()
    learnings = memory.read_learnings()
    decisions = memory.read_decisions()
    if facts or learnings or decisions:
        def _recent(text: str, n: int = 15) -> str:
            lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
            return "\n".join(lines[:n])
        mem_context = f"\n\nShared blackboard context:\nFacts:\n{_recent(facts)}\nLearnings:\n{_recent(learnings)}\nDecisions:\n{_recent(decisions)}"

    brand_constraints = memory._get_memory_dir() / "brand-constraints.md"
    if brand_constraints.exists():
        constraints_text = brand_constraints.read_text(encoding="utf-8")[:2000]
        mem_context += f"\n\nExisting brand constraints:\n{constraints_text}"

    system = SYSTEM_PROMPT + mem_context
    messages: list[dict[str, str]] = [{"role": "user", "content": initial_message}]

    try:
        yield {"type": "session_id", "session_id": sid}
        yield {"type": "status", "content": "Brand Agent thinking..."}

        for round_num in range(30):
            resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.3)

            content = resp.get("content", "")
            tool_calls = resp.get("tool_calls", [])

            if content:
                messages.append({"role": "assistant", "content": content})
                session_data["messages"].append({"role": "assistant", "content": content})
                chunk_size = 30
                for i in range(0, len(content), chunk_size):
                    yield {"type": "text", "content": content[i:i+chunk_size]}

            if not tool_calls:
                break

            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]

                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": tool_args,
                }
                yield {"type": "status", "content": f"Running {tool_name}..."}

                try:
                    result = TOOL_CALLABLES[tool_name](**tool_args)
                    result_str = llm.format_json(result)
                    success = "error" not in result if isinstance(result, dict) else True
                except Exception as e:
                    result = {"error": str(e)}
                    result_str = json.dumps({"error": str(e)})
                    success = False

                session_data["tool_results"].append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                    "success": success,
                })

                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "result": result if isinstance(result, dict) else {"result": str(result)},
                    "success": success,
                }

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", f"call_{round_num}"),
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args, default=str),
                        },
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{round_num}"),
                    "content": result_str,
                })

        session_store.save_session(sid, session_data)
        memory.post_task(f"Brand agent run: {initial_message[:80]}", agent=AGENT_NAME)
        memory.complete_task(f"Brand agent run: {initial_message[:80]}", agent=AGENT_NAME)
        yield {"type": "done"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "error", "content": str(e)}
