"""SEO Agent orchestrator — uses Qwen function calling to pick and chain tools."""
from __future__ import annotations

import json
from typing import Any

from . import llm
from . import memory
from . import session as session_store
from .tools.extract_seeds import extract_seeds
from .tools.pull_universe import pull_universe
from .tools.cluster_keywords import cluster_keywords
from .tools.score_clusters import score_clusters
from .tools.recommend_pillars import recommend_pillars
from .tools.plan_calendar import plan_calendar
from .tools.generate_draft import generate_draft
from .tools.preflight_draft import preflight_draft
from .tools.seo_linter import seo_linter
from .tools.geo_scorer import geo_scorer
from .tools.technical_seo import technical_seo_audit
from .tools.indexnow import submit_indexnow, submit_single_url
from .tools.bing_wmt import get_site_keywords, submit_url as bing_submit_url
from .tools.web_search import web_search
from .tools.memory_tools import (
    read_memory, record_fact, record_learning, record_decision,
    tool_post_task, tool_complete_task, tool_record_artefact, tool_draft_run_summary
)
from .tools.run_discovery import run_discovery
from .tools.gsc import gsc_performance, gsc_submit_sitemap, gsc_list_sitemaps, gsc_inspect_url, gsc_list_sites
from .tools.braintrust import log_conversation, suggest_improvements


SYSTEM_PROMPT = """You are a versatile SEO agent. You help businesses grow through
data-driven content strategy, technical SEO audits, and more.

You have access to the following tools. Use them to accomplish the user's goals.
Think step-by-step. Always explain your reasoning between tool calls.

When a new user needs SEO help, start with run_discovery to gather their business intake.

When you have a business intake:
1. Extract keyword seeds from the business description
2. Pull keyword universe from DataForSEO
3. Cluster keywords into themes
4. Score clusters by SEO + GEO opportunity
5. Recommend content pillars
6. Plan a content calendar
7. Generate drafts for top-priority articles
8. Run SEO lint and GEO scoring on each draft

When asked to audit a site, run the technical SEO audit.
When asked to submit URLs for indexing, use IndexNow or Bing submission.
When asked to research a topic, use web search.
When asked about search performance or indexing, use Google Search Console tools (gsc_performance, gsc_inspect_url, gsc_list_sitemaps, gsc_submit_sitemap, gsc_list_sites).

You have memory tools to read and record information:
- read_memory: Load facts/learnings/decisions/tasks from the blackboard (already loaded at run start, but you can refresh if needed)
- record_fact: Record an observed truth (e.g., "User's blog has 5 posts")
- record_learning: Record a pattern or rule learned (e.g., "Staggering publication dates looks more natural to Google")
- record_decision: Record a choice made and why (e.g., "Using Astro over WordPress for full SEO control")
- post_task: Post a task to the blackboard
- complete_task: Mark a task as completed
- record_artefact: Record a durable deliverable
- draft_run_summary: Draft a run summary (you can call this mid-run when you sense a run is wrapping up)

Use memory tools to:
- Check past context before making decisions (read_memory)
- Record important findings as you work (record_fact/learning/decision)
- Track your work (post_task/complete_task)
- Build up knowledge across runs

After each significant action, summarize what you found and what's next."""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "extract_seeds",
            "description": "Extract keyword seeds from a business description",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_description": {"type": "string"},
                    "site_description": {"type": "string", "default": ""},
                    "competitor_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["business_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pull_universe",
            "description": "Expand keyword seeds into full keyword universe using DataForSEO",
            "parameters": {
                "type": "object",
                "properties": {
                    "seeds": {"type": "object"},
                    "location_code": {"type": "integer", "default": 2840},
                    "language_code": {"type": "string", "default": "en"},
                    "competitor_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["seeds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cluster_keywords",
            "description": "Cluster keywords into thematic groups",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "object"}},
                    "max_clusters": {"type": "integer", "default": 8},
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_clusters",
            "description": "Score clusters for SEO and GEO opportunity",
            "parameters": {
                "type": "object",
                "properties": {
                    "clusters": {"type": "object"},
                },
                "required": ["clusters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_pillars",
            "description": "Select best clusters as content pillars",
            "parameters": {
                "type": "object",
                "properties": {
                    "scored_clusters": {"type": "object"},
                },
                "required": ["scored_clusters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_calendar",
            "description": "Create content calendar from pillars",
            "parameters": {
                "type": "object",
                "properties": {
                    "pillars": {"type": "object"},
                    "weeks": {"type": "integer", "default": 6},
                    "articles_per_week": {"type": "integer", "default": 1},
                },
                "required": ["pillars"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_draft",
            "description": "Generate article draft for a calendar item",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_title": {"type": "string"},
                    "primary_keyword": {"type": "string"},
                    "secondary_keywords": {"type": "array", "items": {"type": "string"}},
                    "content_type": {"type": "string", "default": "guide"},
                    "target_words": {"type": "integer", "default": 1500},
                    "angle": {"type": "string", "default": ""},
                },
                "required": ["article_title", "primary_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preflight_draft",
            "description": "Pre-flight review of article draft before publishing",
            "parameters": {
                "type": "object",
                "properties": {"draft": {"type": "object"}},
                "required": ["draft"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "seo_linter",
            "description": "Lint article for on-page SEO",
            "parameters": {
                "type": "object",
                "properties": {"article": {"type": "object"}},
                "required": ["article"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geo_scorer",
            "description": "Score article for AI citation potential (GEO)",
            "parameters": {
                "type": "object",
                "properties": {"article": {"type": "object"}},
                "required": ["article"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "technical_seo_audit",
            "description": "Run comprehensive technical SEO audit on a URL (24 checks across 9 categories)",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_indexnow",
            "description": "Submit URLs to IndexNow for faster indexing",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "key": {"type": "string"},
                    "key_location": {"type": "string", "default": ""},
                },
                "required": ["urls", "key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bing_submit_url",
            "description": "Submit a URL to Bing for indexing",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {"type": "string"},
                    "page_url": {"type": "string"},
                },
                "required": ["site_url", "page_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_site_keywords",
            "description": "Get top keywords for a site from Bing Webmaster Tools",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {"type": "string"},
                    "count": {"type": "integer", "default": 50},
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "context": {"type": "string", "default": ""},
                },
                "required": ["query"],
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
                    "memory_type": {"type": "string", "enum": ["facts", "learnings", "decisions", "tasks", "all"], "default": "all"},
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
    {
        "type": "function",
        "function": {
            "name": "gsc_performance",
            "description": "Get Google Search Console performance data (clicks, impressions, CTR, position) for a site",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "Site URL as registered in GSC"},
                    "days": {"type": "integer", "default": 28, "description": "Number of days to look back"},
                    "dimensions": {"type": "array", "items": {"type": "string"}, "default": ["query"], "description": "Grouping: query, page, date, device, country"},
                },
                "required": ["site_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gsc_submit_sitemap",
            "description": "Submit a sitemap to Google Search Console",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "Site URL as registered in GSC"},
                    "sitemap_url": {"type": "string", "description": "Full URL of the sitemap"},
                },
                "required": ["site_url", "sitemap_url"],
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
                    "site_url": {"type": "string", "description": "Site URL as registered in GSC"},
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
                    "site_url": {"type": "string", "description": "Site URL as registered in GSC"},
                    "inspection_url": {"type": "string", "description": "The specific URL to inspect"},
                },
                "required": ["site_url", "inspection_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gsc_list_sites",
            "description": "List all sites in the Google Search Console account",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_task",
            "description": "Post a task to the blackboard task board",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_goal": {"type": "string", "description": "What the task aims to accomplish"},
                    "affects": {"type": "string", "default": "", "description": "Files/assets/pages it will touch"},
                },
                "required": ["task_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed on the blackboard",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_goal": {"type": "string", "description": "What the task accomplished"},
                    "affects": {"type": "string", "default": "", "description": "Files/assets/pages it touched"},
                },
                "required": ["task_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_artefact",
            "description": "Record a durable deliverable in the artefacts index",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the artefact"},
                    "summary": {"type": "string", "description": "One-line summary"},
                    "location": {"type": "string", "description": "Where the artefact lives"},
                },
                "required": ["name", "summary", "location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_run_summary",
            "description": "Draft a run summary (can be called mid-run when wrapping up)",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "What this run aimed to accomplish"},
                    "did": {"type": "string", "description": "What was actually done"},
                    "found": {"type": "string", "default": "", "description": "What was discovered"},
                    "artifacts": {"type": "string", "default": "", "description": "Links to any artefact touched"},
                },
                "required": ["goal", "did"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_discovery",
            "description": "Drive an interactive discovery conversation to gather business intake for SEO strategy",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_history": {"type": "array", "items": {"type": "object"}, "description": "List of message dicts with role/content"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_conversation",
            "description": "Log conversation to Braintrust for tracing and analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session identifier"},
                    "messages": {"type": "array", "items": {"type": "object"}},
                    "tool_results": {"type": "array", "items": {"type": "object"}},
                    "metadata": {"type": "object", "default": {}},
                },
                "required": ["session_id", "messages", "tool_results"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_improvements",
            "description": "Analyze a run and suggest improvements to tools, prompts, or setup",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session to analyze"},
                    "conversation_summary": {"type": "string", "description": "Summary of what happened"},
                    "memory_context": {"type": "string", "description": "Current memory state"},
                },
                "required": ["session_id", "conversation_summary"],
            },
        },
    },
]

# Map tool names to actual callables
TOOL_CALLABLES = {
    "extract_seeds": extract_seeds,
    "pull_universe": pull_universe,
    "cluster_keywords": cluster_keywords,
    "score_clusters": score_clusters,
    "recommend_pillars": recommend_pillars,
    "plan_calendar": plan_calendar,
    "generate_draft": generate_draft,
    "preflight_draft": preflight_draft,
    "seo_linter": seo_linter,
    "geo_scorer": geo_scorer,
    "technical_seo_audit": technical_seo_audit,
    "submit_indexnow": submit_indexnow,
    "bing_submit_url": bing_submit_url,
    "get_site_keywords": get_site_keywords,
    "web_search": web_search,
    "read_memory": read_memory,
    "record_fact": record_fact,
    "record_learning": record_learning,
    "record_decision": record_decision,
    "post_task": tool_post_task,
    "complete_task": tool_complete_task,
    "record_artefact": tool_record_artefact,
    "draft_run_summary": tool_draft_run_summary,
    "run_discovery": run_discovery,
    "gsc_performance": gsc_performance,
    "gsc_submit_sitemap": gsc_submit_sitemap,
    "gsc_list_sitemaps": gsc_list_sitemaps,
    "gsc_inspect_url": gsc_inspect_url,
    "gsc_list_sites": gsc_list_sites,
    "log_conversation": log_conversation,
    "suggest_improvements": suggest_improvements,
}


def run_agent(
    user_message: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
    max_rounds: int = 20,
) -> dict[str, Any]:
    """Run the SEO agent with function calling loop."""
    sid = session_id or session_store.new_session_id()
    session_data: dict[str, Any] = {
        "session_id": sid,
        "messages": [],
        "tool_results": [],
        "artifacts": {},
    }

    # Load memory context
    mem_context = ""
    facts = memory.read_facts()
    learnings = memory.read_learnings()
    decisions = memory.read_decisions()
    if facts or learnings or decisions:
        mem_context = f"\n\nMemory context:\nFacts: {facts}\nLearnings: {learnings}\nDecisions: {decisions}"

    system = SYSTEM_PROMPT + mem_context
    if context:
        system += f"\n\nCurrent session context:\n{llm.format_json(context)}"

    messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]

    memory.post_task(user_message[:100])

    for round_num in range(max_rounds):
        resp = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.3)

        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])

        if content:
            messages.append({"role": "assistant", "content": content})
            session_data["messages"].append({"role": "assistant", "content": content})
            print(f"\n[Agent]: {content[:200]}...")

        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc["arguments"]

            print(f"\n[Tool call]: {tool_name}({tool_args[:100]}...)")

            try:
                result = TOOL_CALLABLES[tool_name](
                    **(json.loads(tool_args) if isinstance(tool_args, str) else tool_args)
                )
                result_str = llm.format_json(result)
                session_data["tool_results"].append({
                    "round": round_num,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                })
            except Exception as e:
                result_str = json.dumps({"error": str(e)})
                print(f"[Tool error]: {e}")

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tc],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str[:4000],
            })

    # Save session
    session_store.save_session(sid, session_data)

    # Record to memory
    memory.complete_task(user_message[:100])
    if session_data["tool_results"]:
        tools_used = [t["tool"] for t in session_data["tool_results"]]
        memory.record_fact(f"Run {sid}: used tools {', '.join(set(tools_used))}")

        # Finalize run summary
        tools_summary = ", ".join(sorted(set(tools_used)))
        memory.finalize_run_summary(
            goal=user_message[:100],
            did=f"Used {len(tools_used)} tool calls: {tools_summary}",
            artifacts="see session " + sid,
        )

        # Auto-log to Braintrust if configured
        try:
            log_conversation(
                session_id=sid,
                messages=session_data.get("messages", []),
                tool_results=session_data.get("tool_results", []),
                metadata={"user_request": user_message[:200]},
            )
        except Exception:
            pass  # Braintrust is optional, don't fail the run

    return session_data
