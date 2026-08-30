"""Monitoring Agent — tracks SEO performance, diagnoses issues, generates reports."""
from __future__ import annotations

import json
from typing import Any

from . import llm
from . import memory
from . import session as session_store
from .tools.monitoring_tools import (
    monitor_performance,
    check_indexing_health,
    diagnose_traffic_drop,
    monitor_keyword_rankings,
    content_freshness_alert,
    generate_monitoring_report,
)
from .tools.gsc import gsc_performance, gsc_inspect_url, gsc_list_sitemaps
from .tools.memory_tools import read_memory, record_fact, record_learning, record_decision


AGENT_NAME = "monitoring-agent"


SYSTEM_PROMPT = """You are an SEO Monitoring specialist. You track website performance over time, diagnose traffic changes, and generate actionable reports.

Your capabilities:
- Performance monitoring with bubble chart analysis (monitor_performance)
- Indexing health checks (check_indexing_health)
- Traffic drop diagnosis (diagnose_traffic_drop)
- Keyword ranking tracking (monitor_keyword_rankings)
- Content freshness alerts (content_freshness_alert)
- Comprehensive monitoring reports (generate_monitoring_report)
- Google Search Console access (gsc_performance, gsc_inspect_url, gsc_list_sitemaps)

**Your approach:**
1. Start by understanding what the user wants to monitor
2. Gather current data from multiple sources
3. Compare with historical data when available
4. Identify trends, anomalies, and opportunities
5. Generate clear, actionable recommendations

**Key principles:**
- Always ground analysis in real data from GSC and SERP checks
- Distinguish between normal fluctuations and significant changes
- Prioritize issues by severity (critical > warning > info)
- Provide specific, actionable recommendations — not generic advice
- Track metrics over time to identify trends

You have memory tools to read and record information about monitoring findings.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "monitor_performance",
            "description": "Monitor SEO performance over a period with bubble chart analysis. Compares current vs previous period, identifies gaining/declining/new/lost queries, opportunity queries, and snippet issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "The site URL as registered in GSC",
                    },
                    "days": {
                        "type": "integer",
                        "default": 28,
                        "description": "Number of days to analyze",
                    },
                    "compare_previous": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to compare with the previous period",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_indexing_health",
            "description": "Check indexing health via GSC sitemaps and optional URL inspections. Reports sitemap status, indexed vs submitted counts, errors, and recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "The site URL as registered in GSC",
                    },
                    "sample_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of specific URLs to inspect",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_traffic_drop",
            "description": "Systematically diagnose the cause of a traffic drop. Gathers performance data, checks indexing, cross-references known algorithm updates, and uses LLM analysis to determine root cause.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "The site URL as registered in GSC",
                    },
                    "days_back": {
                        "type": "integer",
                        "default": 30,
                        "description": "Number of days to analyze for the drop",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_keyword_rankings",
            "description": "Track keyword rankings for a domain in organic search results. Reports current position, top-3/top-10 status, and competitor domains ranking above.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "The domain to track (e.g., 'example.com')",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of keywords to check rankings for",
                    },
                    "location_code": {
                        "type": "integer",
                        "default": 2840,
                        "description": "DataForSEO location code (default: 2840 = Bulgaria)",
                    },
                    "language_code": {
                        "type": "string",
                        "default": "en",
                        "description": "Language code for SERP results",
                    },
                },
                "required": ["domain", "keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_freshness_alert",
            "description": "Check content freshness for a list of URLs and alert on stale content. Extracts date signals from pages and compares against threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "Base site URL for context",
                    },
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to check for freshness",
                    },
                    "stale_threshold_months": {
                        "type": "integer",
                        "default": 6,
                        "description": "Months after which content is considered stale",
                    },
                },
                "required": ["site_url", "urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_monitoring_report",
            "description": "Generate a comprehensive monitoring report combining performance, indexing, rankings, and freshness data. Produces health score, executive summary, alerts, and prioritized action items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "The site URL",
                    },
                    "performance_data": {
                        "type": "object",
                        "description": "Output from monitor_performance",
                    },
                    "indexing_data": {
                        "type": "object",
                        "description": "Output from check_indexing_health",
                    },
                    "rankings_data": {
                        "type": "object",
                        "description": "Output from monitor_keyword_rankings",
                    },
                    "freshness_data": {
                        "type": "object",
                        "description": "Output from content_freshness_alert",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gsc_performance",
            "description": "Get Google Search Console performance data (clicks, impressions, CTR, position) for a site",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "Site URL as registered in GSC",
                    },
                    "days": {
                        "type": "integer",
                        "default": 28,
                        "description": "Number of days to look back",
                    },
                    "dimensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["query"],
                        "description": "Grouping: query, page, date, device, country",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gsc_inspect_url",
            "description": "Inspect a URL's indexing status in Google Search Console",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "Site URL as registered in GSC",
                    },
                    "inspection_url": {
                        "type": "string",
                        "description": "The specific URL to inspect",
                    },
                },
                "required": ["site_url", "inspection_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gsc_list_sitemaps",
            "description": "List all sitemaps submitted to Google Search Console",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {
                        "type": "string",
                        "description": "Site URL as registered in GSC",
                    },
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read memory from the blackboard system (facts, learnings, decisions, tasks)",
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
            "description": "Record an observed truth (what IS, was, or happened)",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learning",
            "description": "Record a concluded rule or pattern (what WORKS or is TRUE based on experience)",
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
            "description": "Record a choice made and why (what we CHOSE to do)",
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
    "monitor_performance": monitor_performance,
    "check_indexing_health": check_indexing_health,
    "diagnose_traffic_drop": diagnose_traffic_drop,
    "monitor_keyword_rankings": monitor_keyword_rankings,
    "content_freshness_alert": content_freshness_alert,
    "generate_monitoring_report": generate_monitoring_report,
    "gsc_performance": gsc_performance,
    "gsc_inspect_url": gsc_inspect_url,
    "gsc_list_sitemaps": gsc_list_sitemaps,
    "read_memory": read_memory,
    "record_fact": record_fact,
    "record_learning": record_learning,
    "record_decision": record_decision,
}


def run_monitoring_agent(
    user_message: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
    max_rounds: int = 20,
) -> dict[str, Any]:
    """Run the monitoring agent with function calling loop."""
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
        mem_context = (
            f"\n\nShared blackboard context:\n"
            f"Facts:\n{_recent(facts)}\n"
            f"Learnings:\n{_recent(learnings)}\n"
            f"Decisions:\n{_recent(decisions)}"
        )

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
            print(f"\n[Monitoring Agent]: {content[:200]}...")

        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]

            print(f"\n[Monitoring Tool call]: {tool_name}({json.dumps(tool_args, default=str)[:100]}...)")

            try:
                result = TOOL_CALLABLES[tool_name](**tool_args)
                result_str = llm.format_json(result)
            except Exception as e:
                print(f"[Monitoring Tool error]: {tool_name}: {e}")
                result = {"error": str(e)}
                result_str = json.dumps({"error": str(e)})

            session_data["tool_results"].append({
                "round": round_num,
                "tool": tool_name,
                "args": tool_args,
                "result": result,
                "success": "error" not in result if isinstance(result, dict) else True,
                "error": None if ("error" not in (result if isinstance(result, dict) else {})) else str(result.get("error")),
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
                "content": result_str[:4000],
            })

    # Save session
    session_store.save_session(sid, session_data)

    # Record run summary
    memory.post_task(f"Monitoring agent run: {user_message[:80]}", agent=AGENT_NAME)
    memory.complete_task(f"Monitoring agent run: {user_message[:80]}", agent=AGENT_NAME)

    return session_data
