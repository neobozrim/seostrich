"""CLI entry point for the SEO agent."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .agent import SYSTEM_PROMPT, TOOL_CALLABLES, TOOL_DEFINITIONS
from . import llm
from . import memory


def main():
    parser = argparse.ArgumentParser(
        description="SEO Agent — Multi-agent system with orchestrator layer"
    )
    sub = parser.add_subparsers(dest="command")

    # Main chat interface (always goes through orchestrator)
    chat_p = sub.add_parser("chat", help="Chat with the orchestrator (routes to specialist agents)")
    chat_p.add_argument("--message", "-m", help="Initial message")
    chat_p.add_argument("--session", "-s", help="Resume a session ID")

    # Strategy from intake
    strat_p = sub.add_parser("strategy", help="Run full SEO strategy from intake YAML")
    strat_p.add_argument("--intake", required=True, help="Path to intake YAML file")
    strat_p.add_argument("--skip-drafts", action="store_true", help="Skip article draft generation")
    strat_p.add_argument("--session-out", help="Save session JSON to this path")

    # Technical audit (direct to SEO agent for quick audit)
    audit_p = sub.add_parser("audit", help="Run technical SEO audit")
    audit_p.add_argument("url", help="URL to audit")

    # Discovery
    disc_p = sub.add_parser("discover", help="Interactive business discovery")

    # Submit URL for indexing
    idx_p = sub.add_parser("index", help="Submit URL for indexing (IndexNow)")
    idx_p.add_argument("url", help="URL to submit")
    idx_p.add_argument("--key", required=True, help="IndexNow key")

    # Review improvement proposals
    review_p = sub.add_parser("review", help="Review improvement proposals")

    # Self-learning on demand
    learn_p = sub.add_parser("learn", help="Run self-learning on a specific session")
    learn_p.add_argument("session_id", help="Session ID to analyze")

    # Self-learning on recent sessions
    learn_all_p = sub.add_parser("learn-all", help="Run self-learning on recent sessions")

    # Memory compression
    compress_p = sub.add_parser("compress", help="Compress memory files (archive old entries)")
    compress_p.add_argument("--keep", type=int, default=10, help="Number of recent entries to keep (default: 10)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "chat":
        # Always use orchestrator for chat
        from .orchestrator import run_orchestrator
        run_orchestrator(initial_message=args.message, session_id=args.session)

    elif args.command == "strategy":
        intake_path = Path(args.intake)
        if not intake_path.exists():
            print(f"Intake file not found: {intake_path}")
            sys.exit(1)

        with open(intake_path, encoding="utf-8") as f:
            intake = yaml.safe_load(f)

        message = _build_strategy_prompt(intake, skip_drafts=args.skip_drafts)
        # Strategy goes through orchestrator
        from .orchestrator import run_orchestrator
        run_orchestrator(initial_message=message)

    elif args.command == "audit":
        # Audit goes through orchestrator
        from .orchestrator import run_orchestrator
        run_orchestrator(initial_message=f"Run a technical SEO audit on {args.url}")

    elif args.command == "discover":
        _interactive_discover()

    elif args.command == "index":
        # Indexing goes through orchestrator
        from .orchestrator import run_orchestrator
        run_orchestrator(initial_message=f"Submit this URL for indexing via IndexNow: {args.url} with key {args.key}")

    elif args.command == "review":
        from .improvements import review_proposals
        review_proposals()

    elif args.command == "learn":
        from .tools.self_learning import run_self_learning
        result = run_self_learning(args.session_id)
        print(f"\nSelf-learning result: {json.dumps(result, indent=2)}")

    elif args.command == "learn-all":
        from .tools.self_learning import run_self_learning_on_demand
        result = run_self_learning_on_demand()
        print(f"\nSelf-learning result: {json.dumps(result, indent=2)}")

    elif args.command == "compress":
        from .tools.memory_compression import compress_all_memory_files
        print(f"Compressing memory files (keeping {args.keep} recent entries)...")
        results = compress_all_memory_files(keep_recent=args.keep)
        for filename, count in results.items():
            print(f"  {filename}: archived {count} entries")
        print(f"\nTotal archived: {sum(results.values())} entries")


def _build_system_prompt() -> str:
    """Build system prompt with recent memory context."""
    mem_context = ""
    facts = memory.read_facts()
    learnings = memory.read_learnings()
    decisions = memory.read_decisions()
    if facts or learnings or decisions:
        def _recent(text: str, n: int = 10) -> str:
            lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
            return "\n".join(lines[:n])
        mem_context = f"\n\nMemory context (most recent):\nFacts:\n{_recent(facts)}\nLearnings:\n{_recent(learnings)}\nDecisions:\n{_recent(decisions)}"
    return SYSTEM_PROMPT + mem_context


def _interactive_chat(initial_message: str | None = None):
    """Run a persistent interactive chat loop with the agent."""
    print("\n" + "=" * 60)
    print("SEO Agent (type 'exit' or Ctrl+C to quit)")
    print("=" * 60)

    system = _build_system_prompt()
    messages: list[dict[str, str]] = []
    session_id = None
    all_tool_results: list[dict] = []
    round_num = 0

    # Get first message
    if initial_message:
        user_input = initial_message
        print(f"\n[You]: {user_input}")
    else:
        try:
            user_input = input("\n[You]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return
        if not user_input:
            print("Goodbye!")
            return

    # Main conversation loop
    while True:
        if user_input.lower() in ('exit', 'quit', 'q'):
            print("\nGoodbye!")
            break

        messages.append({"role": "user", "content": user_input})
        memory.post_task(user_input[:100])

        # Process agent turn (may involve multiple tool calls)
        turn_tool_results = []
        for _ in range(20):  # Max 20 tool call rounds per turn
            try:
                resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.3)
            except Exception as e:
                print(f"\n[Error]: LLM call failed: {e}")
                # Log the error to Braintrust if available
                try:
                    from .tools.braintrust import log_conversation
                    log_conversation(
                        session_id=f"error-{round_num}",
                        messages=messages[-5:],  # Last 5 messages for context
                        tool_results=turn_tool_results,
                        metadata={"error": str(e), "user_request": user_input[:200]},
                    )
                except Exception:
                    pass
                break

            content = resp.get("content", "")
            tool_calls = resp.get("tool_calls", [])

            if content:
                messages.append({"role": "assistant", "content": content})
                print(f"\n[Agent]: {content}")

            if not tool_calls:
                break

            # Collect all tool results first
            tool_results_this_round = []
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["arguments"]

                print(f"\n[Tool]: {tool_name}({tool_args[:100]}...)")

                try:
                    result = TOOL_CALLABLES[tool_name](
                        **(json.loads(tool_args) if isinstance(tool_args, str) else tool_args)
                    )
                    result_str = llm.format_json(result)
                    turn_tool_results.append({
                        "round": round_num,
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    })
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    print(f"[Tool error]: {e}")

                tool_results_this_round.append((tc, result_str))

            # Add ONE assistant message with ALL tool_calls (OpenAI format)
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    }
                    for tc, _ in tool_results_this_round
                ],
            })

            # Add individual tool result messages
            for tc, result_str in tool_results_this_round:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str[:4000],
                })

        all_tool_results.extend(turn_tool_results)
        round_num += 1

        # Auto-log to Braintrust after each turn
        if turn_tool_results:
            try:
                from .tools.braintrust import log_conversation
                sid = session_id or f"chat-{round_num}"
                log_conversation(
                    session_id=sid,
                    messages=[{"role": "user", "content": user_input}] + [m for m in messages if m.get("role") == "assistant" and m.get("content")],
                    tool_results=turn_tool_results,
                    metadata={"user_request": user_input[:200]},
                )
            except Exception:
                pass

            # Record run summary
            try:
                tools_summary = ", ".join(sorted(set(t["tool"] for t in turn_tool_results)))
                memory.finalize_run_summary(
                    goal=user_input[:100],
                    did=f"Used {len(turn_tool_results)} tool calls: {tools_summary}",
                    artifacts="see session",
                )
            except Exception:
                pass

        # Get next user input
        try:
            user_input = input("\n[You]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

    # Final memory synthesis
    if all_tool_results:
        try:
            from .tools.memory_synthesis import synthesize_memories_from_session
            print("\n[Memory Synthesis] Extracting learnings...")
            synthesis_result = synthesize_memories_from_session(
                session_id="chat-session",
                messages=messages,
                tool_results=all_tool_results,
            )
            if synthesis_result.get("status") == "success":
                print(f"  ✓ Extracted {synthesis_result.get('facts_count', 0)} facts")
                print(f"  ✓ Extracted {synthesis_result.get('learnings_count', 0)} learnings")
                print(f"  ✓ Extracted {synthesis_result.get('decisions_count', 0)} decisions")
        except Exception as e:
            print(f"  ⚠ Memory synthesis failed: {e}")

    print(f"\nSession: {len(all_tool_results)} tool calls across {round_num} turns")


def _interactive_discover():
    """Run discovery then transition to persistent chat."""
    print("Starting interactive SEO discovery...")
    print("The agent will ask questions to understand your business.\n")
    from .tools.run_discovery import run_discovery

    history = []
    intake = None
    while True:
        result = run_discovery(history)
        if result.get("status") == "complete":
            intake = result.get("intake", {})
            print("\n✓ Discovery complete! Business intake:")
            print(json.dumps(intake, indent=2))
            break
        elif result.get("status") == "asking":
            print(f"\n[Agent]: {result.get('question', '')}")
            try:
                user_input = input("\n[You]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nDiscovery cancelled.")
                return
            history.append({"role": "assistant", "content": result.get("question", "")})
            history.append({"role": "user", "content": user_input})
        else:
            print(f"\n[Agent]: {result}")
            break

    # Transition to persistent chat with business context
    if intake:
        print("\n" + "=" * 60)
        print("Business context loaded. Starting chat session.")
        print("=" * 60)

        # Build context message with intake
        context_msg = f"Business context:\n{json.dumps(intake, indent=2)}\n\nWhat would you like to accomplish?"
        print(f"\n[Agent]: {context_msg}")

        # Start interactive chat with this context
        _interactive_chat(initial_message=None)


def _build_strategy_prompt(intake: dict, *, skip_drafts: bool = False) -> str:
    domain = intake.get("domain", "")
    description = intake.get("description", "")
    goal = intake.get("goal", "")
    locale = intake.get("locale", {})
    competitors = intake.get("competitors", [])
    notes = intake.get("notes", "")
    opt_mix = intake.get("optimization_mix", "balanced")

    loc_code = locale.get("location_code", 2840) if isinstance(locale, dict) else 2840
    lang_code = locale.get("language_code", "en") if isinstance(locale, dict) else "en"

    prompt = f"""Run a full SEO strategy for this business:

Domain: {domain}
Description: {description}
Goal: {goal}
Locale: location_code={loc_code}, language_code={lang_code}
Competitors: {json.dumps(competitors)}
Optimization mix: {opt_mix}
Notes: {notes}

Steps:
1. Extract keyword seeds
2. Pull keyword universe from DataForSEO
3. Cluster keywords into themes
4. Score clusters by SEO + GEO opportunity
5. Recommend content pillars
6. Plan a content calendar"""

    if not skip_drafts:
        prompt += "\n7. Generate a draft for the first article\n8. Run SEO lint and GEO scoring on the draft"

    return prompt


def _print_result(result: dict):
    print("\n" + "=" * 60)
    print("SESSION COMPLETE")
    print("=" * 60)
    print(f"Session ID: {result.get('session_id', 'N/A')}")
    print(f"Tool calls: {len(result.get('tool_results', []))}")
    tools = set(t['tool'] for t in result.get('tool_results', []))
    if tools:
        print(f"Tools used: {', '.join(sorted(tools))}")
    print("=" * 60)


if __name__ == "__main__":
    main()
