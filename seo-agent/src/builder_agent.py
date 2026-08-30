"""Builder Agent — autonomous builder with 3-tier verification.

Owns: implementation, asset generation, verification.
Reads: brand_profile.json, content_plan.md from artefacts.
Emits: code, images, verified deployments.

Three verification tiers:
1. Mechanical (build success, zero errors, no overflow)
2. Compliance (computed styles match brand tokens — HARD GATE)
3. Judgment (LLM assesses: does it read as intended mode?)

Builder never changes the brand profile. If Tier 2 fails, builder adjusts
implementation, not the profile.
"""
from __future__ import annotations

import json
from typing import Any

from . import llm
from . import memory
from . import session as session_store
from .builder_tools import (
    read_brand_profile,
    read_content_plan,
    write_file,
    run_shell,
    playwright_check,
    take_screenshot,
)
from .asset_tools import generate_asset
from .tools.web_search import web_search
from .tools.memory_tools import read_memory, record_fact, record_learning, record_decision

AGENT_NAME = "builder-agent"


SYSTEM_PROMPT = """You are a builder agent specializing in autonomous implementation with rigorous verification.

You operate with full autonomy on implementation details but are hard-constrained
on identity: you never change the brand profile. If compliance checks fail,
you adjust your implementation, not the profile.

## Your process — do not skip tiers

1. READ CONTEXT. Load brand_profile.json and content_plan.md from artefacts.
   These are your constraints. You do not negotiate them.

2. BUILD. Implement the requested work using your tools:
   - write_file: create code, configs, content
   - run_shell: install deps, build, test
   - generate_image: create assets via fal.ai (Ideogram for wordmarks, Recraft for SVG, Flux for photoreal)

3. VERIFY — THREE TIERS (in order, never skip):

   Tier 1: Mechanical
   - Build succeeds (zero compilation/bundle errors)
   - Zero console errors in browser
   - No failed network requests
   - No layout overflow at 360px, 768px, 1440px
   - If any fail: fix and re-check Tier 1 before proceeding

   Tier 2: Compliance (HARD GATE)
   - Computed styles match brand tokens:
     * Colors match brand_profile.json (base, primary, accent)
     * Typography matches brand_profile.json (primary/secondary families)
     * Contrast ratios pass WCAG AA (4.5:1 for text, 3:1 for large text)
     * No items from exclusion_list present
     * Headlines are real DOM text (not baked into images)
     * Voice constraints respected (no banned words, correct casing)
   - If ANY fail: STOP. This is a hard gate.
     You must fix your implementation to match the brand profile.
     You do NOT change the brand profile to match your implementation.
   - Only proceed to Tier 3 when Tier 2 passes completely

   Tier 3: Judgment
   - Take screenshot of the implementation
   - Ask yourself: does this read as the intended mode (handmade/bold)?
   - Does it look templated? Generic? Corporate?
   - Does it feel like a real person/team made this, or like it came from a template?
   - Document your judgment and any refinements needed
   - This is soft — use your best assessment

## Asset generation

You have access to image generation models via fal.ai:
- Ideogram 3.0: wordmarks, logos with text (best for type-heavy assets)
- Recraft V4: SVG/vector output (best for icons, illustrations)
- Flux 2 Pro: photorealistic images (best for hero images, backgrounds)
- Imagen 4 Fast: bulk drafts, concept exploration

Routing rules:
- Wordmark/logo → Ideogram 3.0
- Icon/illustration → Recraft V4
- Photoreal/hero image → Flux 2 Pro
- Bulk exploration → Imagen 4 Fast
- FLUX dev models → reject for commercial use (route to Pro)
- Recraft free tier → warn if output is for commercial use

All generated images inherit brand tokens:
- Colors from brand_profile.json
- Typography style from brand_profile.json
- Texture/grade from brand_profile.json

## Honesty constraints

- If you cannot achieve Tier 2 compliance, say so explicitly
- If Tier 3 judgment is "this looks templated," document why and suggest alternatives
- If an asset generation model fails, try fallback models before giving up
- If you need to make a trade-off between Tier 1 (mechanical) and Tier 2 (compliance), Tier 2 wins

## Tools available

- read_brand_profile: load brand_profile.json from artefacts
- read_content_plan: load content_plan.md from artefacts
- write_file: create code, configs, content
- run_shell: install deps, build, test
- playwright_check: run 3-tier verification on a URL
- take_screenshot: capture screenshot for Tier 3 judgment
- generate_image: create assets via fal.ai (specify model: ideogram/recraft/flux/imagen)
- web_search: research, reference gathering
- read_memory: read shared blackboard
- record_fact/learning/decision: update shared blackboard

## Output

When you complete a build:
1. Report Tier 1 status (pass/fail + details)
2. Report Tier 2 status (pass/fail + compliance check results)
3. Report Tier 3 judgment (screenshot + assessment)
4. List any refinements needed
5. Record learnings and decisions to the blackboard

If you fail Tier 2, you must explicitly state:
- Which compliance checks failed
- What you tried to fix
- Why you could not achieve compliance (if applicable)
- Recommendation for next steps
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_brand_profile",
            "description": "Load brand_profile.json from artefacts (immutable constraints)",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client ID (e.g., 'unblocked')"},
                },
                "required": ["client_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_content_plan",
            "description": "Load content_plan.md from artefacts",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client ID"},
                },
                "required": ["client_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or update a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command (install, build, test)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command"},
                    "cwd": {"type": "string", "description": "Working directory (optional)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_check",
            "description": "Run 3-tier verification on a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to verify"},
                    "checks": {
                        "type": "object",
                        "description": "Verification checks: tier1, tier2 (with brand_profile), tier3",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture screenshot for Tier 3 judgment",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to screenshot"},
                    "output_path": {"type": "string", "description": "Output file path"},
                },
                "required": ["url", "output_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_asset",
            "description": "Generate image asset via fal.ai with automatic model selection (wordmark/logo/icon/illustration/photo/hero/background)",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Image prompt"},
                    "asset_type": {
                        "type": "string",
                        "description": "Type of asset (wordmark/logo/icon/illustration/vector/svg/photo/photoreal/hero/background/draft/concept/bulk)",
                    },
                    "brand_profile": {"type": "object", "description": "Brand profile with colors/typography/texture to inject"},
                    "params": {"type": "object", "description": "Additional model parameters"},
                    "commercial": {"type": "boolean", "description": "Whether output will be used commercially"},
                },
                "required": ["prompt", "asset_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for research or references",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read shared blackboard",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learning",
            "description": "Record a learned pattern to the blackboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "learning": {"type": "string"},
                },
                "required": ["learning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_decision",
            "description": "Record a decision to the blackboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                },
                "required": ["decision"],
            },
        },
    },
]


TOOL_CALLABLES = {
    "read_brand_profile": read_brand_profile,
    "read_content_plan": read_content_plan,
    "write_file": write_file,
    "run_shell": run_shell,
    "playwright_check": playwright_check,
    "take_screenshot": take_screenshot,
    "generate_asset": generate_asset,
    "web_search": web_search,
    "read_memory": read_memory,
    "record_learning": record_learning,
    "record_decision": record_decision,
}


def run_builder_agent(
    user_message: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
    max_rounds: int = 50,
) -> dict[str, Any]:
    """Run the Builder Agent with function calling loop.

    Higher max_rounds (50) because builder may need multiple iterations
    to achieve Tier 2 compliance.
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

    system = SYSTEM_PROMPT + mem_context
    if context:
        system += f"\n\nAdditional context:\n{llm.format_json(context)}"

    messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]

    for round_num in range(max_rounds):
        resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.2)

        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])

        if content:
            messages.append({"role": "assistant", "content": content})
            session_data["messages"].append({"role": "assistant", "content": content})
            print(f"\n[Builder Agent]: {content[:200]}...")

        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]

            print(f"\n[Builder Tool call]: {tool_name}({json.dumps(tool_args, default=str)[:100]}...)")

            try:
                result = TOOL_CALLABLES[tool_name](**tool_args)
                result_str = llm.format_json(result)
            except Exception as e:
                print(f"[Builder Tool error]: {tool_name}: {e}")
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
    memory.post_task(f"Builder agent run: {user_message[:80]}", agent=AGENT_NAME)
    memory.complete_task(f"Builder agent run: {user_message[:80]}", agent=AGENT_NAME)

    return session_data


def run_builder_agent_stream(
    initial_message: str,
    session_id: str | None = None,
):
    """Run the Builder Agent as a streaming generator.
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

    system = SYSTEM_PROMPT + mem_context
    messages: list[dict[str, str]] = [{"role": "user", "content": initial_message}]

    try:
        yield {"type": "session_id", "session_id": sid}
        yield {"type": "status", "content": "Builder Agent working..."}

        for round_num in range(50):
            resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.2)

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
        memory.post_task(f"Builder agent run: {initial_message[:80]}", agent=AGENT_NAME)
        memory.complete_task(f"Builder agent run: {initial_message[:80]}", agent=AGENT_NAME)
        yield {"type": "done"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "error", "content": str(e)}
