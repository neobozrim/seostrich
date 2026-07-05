"""CLI entry point for the SEO agent."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .agent import run_agent


def main():
    parser = argparse.ArgumentParser(
        description="Versatile SEO Agent — keyword research, content strategy, technical audit, competitor analysis"
    )
    sub = parser.add_subparsers(dest="command")

    # Interactive chat
    chat_p = sub.add_parser("chat", help="Interactive chat with the SEO agent")
    chat_p.add_argument("--message", "-m", help="Initial message")
    chat_p.add_argument("--session", "-s", help="Resume a session ID")

    # Strategy from intake
    strat_p = sub.add_parser("strategy", help="Run full SEO strategy from intake YAML")
    strat_p.add_argument("--intake", required=True, help="Path to intake YAML file")
    strat_p.add_argument("--skip-drafts", action="store_true", help="Skip article draft generation")
    strat_p.add_argument("--session-out", help="Save session JSON to this path")

    # Technical audit
    audit_p = sub.add_parser("audit", help="Run technical SEO audit")
    audit_p.add_argument("url", help="URL to audit")

    # Competitor analysis
    comp_p = sub.add_parser("competitor", help="Analyze a competitor")
    comp_p.add_argument("url", help="Competitor URL")
    comp_p.add_argument("--our-domain", default="", help="Our domain for comparison")
    comp_p.add_argument("--our-description", default="", help="Our business description")

    # Submit URL for indexing
    idx_p = sub.add_parser("index", help="Submit URL for indexing (IndexNow)")
    idx_p.add_argument("url", help="URL to submit")
    idx_p.add_argument("--key", required=True, help="IndexNow key")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "chat":
        msg = args.message or input("Enter your SEO question: ")
        result = run_agent(msg, session_id=args.session)
        _print_result(result)

    elif args.command == "strategy":
        intake_path = Path(args.intake)
        if not intake_path.exists():
            print(f"Intake file not found: {intake_path}")
            sys.exit(1)

        with open(intake_path) as f:
            intake = yaml.safe_load(f)

        message = _build_strategy_prompt(intake, skip_drafts=args.skip_drafts)
        result = run_agent(message)
        _print_result(result)

        if args.session_out:
            Path(args.session_out).parent.mkdir(parents=True, exist_ok=True)
            with open(args.session_out, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\nSession saved to {args.session_out}")

    elif args.command == "audit":
        result = run_agent(f"Run a technical SEO audit on {args.url}")
        _print_result(result)

    elif args.command == "competitor":
        msg = f"Analyze competitor {args.url}"
        if args.our_domain:
            msg += f" compared to our domain {args.our_domain}"
        if args.our_description:
            msg += f". Our business: {args.our_description}"
        result = run_agent(msg)
        _print_result(result)

    elif args.command == "index":
        result = run_agent(f"Submit this URL for indexing via IndexNow: {args.url} with key {args.key}")
        _print_result(result)


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
