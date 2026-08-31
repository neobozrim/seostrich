"""SEO Agent orchestrator — uses Qwen function calling to pick and chain tools."""
from __future__ import annotations

import json
from typing import Any

from . import llm
from . import memory
from . import pipeline_recorder
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
    tool_record_artefact, tool_draft_run_summary
)
from .tools.run_discovery import run_discovery
from .tools.gsc import gsc_performance, gsc_submit_sitemap, gsc_list_sitemaps, gsc_inspect_url, gsc_list_sites
from .tools.braintrust import log_conversation, suggest_improvements
from .tools.dataforseo import ai_mentions

# --- New audit suite (split from technical_seo_audit) ---
from .tools.audit_crawlability import audit_crawlability
from .tools.audit_meta_tags import audit_meta_tags
from .tools.audit_structured_data import audit_structured_data
from .tools.audit_performance import audit_performance
from .tools.audit_mobile import audit_mobile
from .tools.audit_i18n import audit_i18n
from .tools.audit_content import audit_content
from .tools.render_and_compare import render_and_compare

# --- New research & analysis tools ---
from .tools.validate_sitemap import validate_sitemap
from .tools.check_redirects import check_redirects
from .tools.internal_link_audit import internal_link_audit
from .tools.duplicate_content_scan import duplicate_content_scan
from .tools.hreflang_validator import hreflang_validator
from .tools.content_quality_assessment import content_quality_assessment
from .tools.content_freshness_scan import content_freshness_scan
from .tools.pagination_audit import pagination_audit
from .tools.validate_clusters import validate_clusters
from .tools.submit_deliverable import submit_deliverable
from .tools.select_clusters import select_clusters
from .tools.cluster_ops import (
    list_clusters_all, promote_cluster, discard_cluster, propose_cluster,
)

# --- Exposed DataForSEO functions (previously internal only) ---
from .tools.dataforseo import (
    serp_organic, serp_ai_mode, keyword_difficulty,
    historical_search_volume, competitors_domain, domain_intersection,
    keywords_for_site,
)

# --- Fallback chains ---
from .tools.fallback_chains import execute_with_fallback, get_fallback_info

AGENT_NAME = "seo-agent"


SYSTEM_PROMPT = """You are a flexible SEO agent. You help businesses grow through data-driven content strategy, technical audits, and more.

Your job is to understand what the user wants to accomplish, then plan the best sequence of tool calls to achieve that goal. Think step-by-step. Always explain your reasoning.

When starting a new conversation, ask what the user wants to accomplish. Then plan your approach based on available tools.

**Your capabilities:**
- Keyword research and clustering (extract_seeds, pull_universe, cluster_keywords, score_clusters)
- Competitive analysis (serp_organic, serp_ai_mode, keyword_difficulty, competitors_domain, domain_intersection, keywords_for_site, historical_search_volume)
- Content strategy (recommend_pillars, plan_calendar, generate_draft, seo_linter, geo_scorer, content_quality_assessment)
- Composable technical audits (audit_crawlability, audit_meta_tags, audit_structured_data, audit_performance, audit_mobile, audit_i18n, audit_content, render_and_compare)
- Legacy full audit (technical_seo_audit — 24 checks in one call)
- Site-wide analysis (validate_sitemap, check_redirects, internal_link_audit, duplicate_content_scan, hreflang_validator, content_freshness_scan, pagination_audit)
- Indexing and submission (submit_indexnow, bing_submit_url, gsc_submit_sitemap)
- Search performance analysis (gsc_performance, gsc_inspect_url, gsc_list_sitemaps, gsc_list_sites)
- AI visibility tracking (ai_mentions, geo_scorer)
- Web search for research (web_search)

**Tool fallbacks:** execute_with_fallback is available for non-data tools only (e.g., technical_seo_audit → composable sub-audits). DataForSEO tools have NO fallbacks — never substitute web_search for keyword/SERP data. If a DataForSEO call fails, retry it ONCE (transient errors only); if it fails again or you hit a budget error, stop calling DataForSEO, report what you have so far, and ask the user how to proceed.

**Composable vs Legacy Audits:**
- **PREFER composable audit tools** (audit_crawlability, audit_meta_tags, audit_structured_data, audit_performance, audit_mobile, audit_i18n, audit_content) over the legacy `technical_seo_audit`.
- Composable tools provide deeper, more detailed analysis and better error handling.
- When running audits, call **multiple composable tools in sequence** to get comprehensive coverage.
- Example: For a full audit, call audit_crawlability → audit_meta_tags → audit_structured_data → audit_performance → audit_mobile, then synthesize findings.
- Only use `technical_seo_audit` if the user explicitly requests a "quick" or "legacy" audit.

**Multi-Tool Chaining:**
- **Always chain multiple tools** when a task requires comprehensive analysis.
- After an initial audit, if issues are found, call additional specialized tools to investigate further.
- Don't stop after one tool call unless the task is truly complete. If you say "let me dig deeper", actually call the next tool.
- Produce a **structured final report** that synthesizes findings from all tools called.

**CRITICAL — Keyword Research Workflow (mandatory validation + governance steps):**
1. extract_seeds → pull_universe → cluster_keywords with max_clusters=10 — OVER-GENERATE on purpose
2. **MANDATORY: validate_clusters** — self-critique the clusters for coherence. If verdict is "needs_revision", revise and re-validate. If "rejected", re-cluster. NEVER proceed without "approved" verdict.
3. score_clusters
4. **select_clusters** — pick the top 3-4 clusters to pursue; every discarded cluster gets a concrete reason. Discarded clusters keep their stats and can be promoted back.
5. recommend_pillars (from the SELECTED clusters only) → plan_calendar ONLY if the user confirms they want a calendar

Cluster governance (user can adjust after the run — same session):
- list_clusters_all: show selected + discarded with reasons
- promote_cluster / discard_cluster: move clusters between the two sets (reversible)
- propose_cluster: new cluster via scoped re-seed on one topic

Bad clusters produce bad pillars produce bad content. validate_clusters is the gate.

**Example workflows (not prescriptive — adapt to user's actual goal):**
- Full SEO strategy: discover business → extract seeds → pull universe → cluster → VALIDATE clusters → score → recommend pillars → plan calendar → draft articles → lint drafts
- Quick content audit: audit site → identify issues → recommend fixes
- Indexing new content: submit URLs to IndexNow → verify in GSC
- Performance analysis: check GSC performance → identify opportunities → suggest optimizations
- AI visibility check: check ai_mentions → analyze geo_scorer → recommend optimizations for AI citations

You have memory tools to read and record information:
- read_memory: Load facts/learnings/decisions/tasks from the blackboard
- record_fact: Record an observed truth (e.g., "User's blog has 5 posts")
- record_learning: Record a pattern or rule learned (e.g., "Staggering publication dates looks more natural to Google")
- record_decision: Record a choice made and why (e.g., "Using Astro over WordPress for full SEO control")
- tool_record_artefact: Record a durable deliverable
- tool_draft_run_summary: Draft a run summary (you can call this mid-run when you sense a run is wrapping up)

**Memory Usage Strategy:**

You use a shared blackboard memory system. Follow the memory-recording skill (loaded at run start) which defines exactly what belongs in each file (facts, learnings, decisions, tasks, run summaries, artefacts) and the quality gates for recording.

Before making decisions, consult memory to understand past context. Use learnings to avoid repeating mistakes. Use decisions to maintain consistency. After every run, run the post-run reflection checklist from the memory-recording skill before finalizing.

**Tool Call Discipline:**

- Do NOT call the same tool twice with identical arguments in succession. If you just called `read_memory`, use the returned data — don't call it again.
- After any tool call, evaluate the output before deciding on the next action. Don't blindly chain tools.
- If a tool returns empty or no results, don't retry with the same arguments. Either change your query or move on.
- Prefer one well-crafted search query over multiple similar queries.
- DataForSEO calls cost money. Batch keywords into a single call whenever a tool accepts a list, never loop one-call-per-keyword when batching exists, and never re-fetch data you already have in this session."""


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
            "description": "Cluster keywords into thematic groups. Over-generate (8-10) — a later select_clusters step cuts to the top 3-4.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "object"}},
                    "max_clusters": {"type": "integer", "default": 10},
                    "location_code": {"type": "integer", "description": "Optional Google Ads location code of the target market (e.g. 2840 US, 2826 UK)"},
                    "language_code": {"type": "string", "description": "Optional language code of the target market (e.g. en)"},
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
            "name": "select_clusters",
            "description": "Governance cut after scoring: pick the top 3-4 clusters to pursue as pillars and record a concrete discard reason for the rest. Run after score_clusters on the over-generated set, BEFORE recommend_pillars.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scored_clusters": {"type": "object", "description": "the score_clusters result"},
                    "max_select": {"type": "integer", "default": 4},
                },
                "required": ["scored_clusters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clusters_all",
            "description": "List selected AND discarded clusters of the active run, with stats and discard reasons. Use before promote/discard/propose ops or when the user asks what was dropped.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "promote_cluster",
            "description": "Promote a discarded cluster back into the selection (reversible governance op).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string"},
                },
                "required": ["cluster_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_cluster",
            "description": "Discard a selected cluster (moves it to the discarded set, stats preserved, reversible).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string"},
                    "reason": {"type": "string", "default": ""},
                },
                "required": ["cluster_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cluster",
            "description": "Propose a NEW cluster the pipeline missed: scoped keyword re-seed on one topic (1 DataForSEO call), assembled deterministically with real volume/difficulty/intent stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                },
                "required": ["topic"],
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
            "name": "submit_deliverable",
            "description": "Submit a deliverable you synthesized (on-page brief, AI-citability brief, recommendations) so it is recorded as a pipeline stage in the Run view. Use for outputs that are not a direct tool result. Only works inside an active pipeline run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_id": {"type": "string", "description": "Stage this belongs to: intake|seeds|keywords|clusters|pillars|mix|audit|competitors|onpage|ai_citability"},
                    "title": {"type": "string"},
                    "artifact": {"type": "object", "description": "The deliverable content as a JSON object"},
                },
                "required": ["stage_id", "title", "artifact"],
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
    {
        "type": "function",
        "function": {
            "name": "ai_mentions",
            "description": "Get AI mentions for a domain - tracks how AI systems (ChatGPT, Claude, etc.) cite/reference the domain",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Target domain (e.g., 'example.com')"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum number of mentions to return"},
                },
                "required": ["domain"],
            },
        },
    },
    # --- Composable Audit Suite ---
    {
        "type": "function",
        "function": {
            "name": "audit_crawlability",
            "description": "Audit crawlability: HTTPS, robots.txt (full parse with AI bot analysis), sitemap, noindex, canonical tags, redirect detection, internal link crawlability, AI crawler blocking, resource blocking. 10 checks.",
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
            "name": "audit_meta_tags",
            "description": "Audit meta tags: title, description, H1, duplicates, Open Graph, Twitter Cards, canonical consistency, viewport, charset, language. 10 checks.",
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
            "name": "audit_structured_data",
            "description": "Audit structured data: JSON-LD presence, Google-supported types, required/recommended properties, deprecated types, schema conflicts, image requirements. 9 checks.",
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
            "name": "audit_performance",
            "description": "Audit performance: Core Web Vitals (LCP/CLS/INP), HSTS, CSP, X-Frame-Options, mixed content, resource count, render-blocking resources. 9 checks.",
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
            "name": "audit_mobile",
            "description": "Audit mobile: viewport, horizontal scroll, touch targets, font size, content width. 5 checks.",
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
            "name": "audit_i18n",
            "description": "Audit internationalization: hreflang tags, bidirectional validation, ISO code validation, URL qualification, method consistency, locale-adaptive detection. 6 checks.",
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
            "name": "audit_content",
            "description": "Audit content: word count, freshness dates, author/E-E-A-T, heading hierarchy, list usage, image optimization, internal/external links, tables, sections. 10 checks.",
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
            "name": "render_and_compare",
            "description": "Analyze raw HTML for JS rendering issues: SPA/SSR detection, critical SEO elements in raw HTML, parity score, recommendations for crawlers that don't execute JS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "wait_seconds": {"type": "integer", "default": 5},
                },
                "required": ["url"],
            },
        },
    },
    # --- Research & Analysis Tools ---
    {
        "type": "function",
        "function": {
            "name": "validate_sitemap",
            "description": "Full sitemap XML validation: URL count limits, lastmod accuracy, namespace correctness, image/video/news extensions, duplicate URLs, common errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sitemap_url": {"type": "string", "description": "Full URL of the sitemap to validate"},
                    "site_url": {"type": "string", "default": "", "description": "Site URL to verify sitemap URLs belong to same domain"},
                },
                "required": ["sitemap_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_redirects",
            "description": "Follow redirect chains and analyze redirect types: 301/302/307/308 classification, loop detection, chain length, mass-redirect-to-homepage, meta-refresh and JS redirects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to check for redirects"},
                    "max_hops": {"type": "integer", "default": 10},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "internal_link_audit",
            "description": "Crawl domain and map link graph: orphan pages, anchor text quality (generic vs descriptive), crawlable vs non-crawlable navigation, deepest pages, link coverage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_url": {"type": "string", "description": "Starting URL for the crawl"},
                    "max_pages": {"type": "integer", "default": 50},
                    "max_depth": {"type": "integer", "default": 3},
                },
                "required": ["start_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "duplicate_content_scan",
            "description": "Detect duplicate/near-duplicate content across URLs using Jaccard similarity on word n-grams. Groups duplicates and recommends canonical URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to compare for content similarity"},
                    "similarity_threshold": {"type": "number", "default": 0.85},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hreflang_validator",
            "description": "Full hreflang validation: bidirectional linking check, ISO 639-1 code validation, region code validation, URL qualification, x-default presence, method consistency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs with hreflang tags to validate"},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_quality_assessment",
            "description": "Evaluate content against E-E-A-T and people-first criteria using LLM analysis: experience, expertise, authoritativeness, trustworthiness, originality, comprehensiveness scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article": {"type": "string", "description": "Article text to evaluate"},
                    "topic": {"type": "string", "default": "", "description": "Topic/domain context"},
                    "author_info": {"type": "string", "default": "", "description": "Author credentials if known"},
                },
                "required": ["article"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_freshness_scan",
            "description": "Scan URLs for content freshness: extract dates from JSON-LD, meta tags, and text patterns. Classify as fresh/stale/unknown based on configurable threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to scan for freshness"},
                    "stale_threshold_months": {"type": "integer", "default": 6},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pagination_audit",
            "description": "Audit pagination implementation: detect method (links/load-more/infinite-scroll), check unique URLs, crawlability, canonical correctness, deprecated rel tags.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Any page in a paginated sequence"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_clusters",
            "description": "CRITICAL: Validate keyword clusters for coherence AFTER cluster_keywords runs. Checks thematic coherence, distinctiveness, content viability, search intent alignment, and strategic value. Returns verdict: approved/needs_revision/rejected. Always run this before score_clusters and recommend_pillars — bad clusters produce bad pillars produce bad content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "clusters": {"type": "object", "description": "Output from cluster_keywords — dict of cluster_name to keyword list"},
                    "seeds": {"type": "object", "default": None, "description": "Original seed keywords for context"},
                    "domain": {"type": "string", "default": "", "description": "Site domain for strategic context"},
                    "domain_description": {"type": "string", "default": "", "description": "Brief description of the business/site"},
                },
                "required": ["clusters"],
            },
        },
    },
    # --- Exposed DataForSEO Tools ---
    {
        "type": "function",
        "function": {
            "name": "serp_organic",
            "description": "Analyze organic search results for a keyword: who ranks, their position, domain, title, description. Useful for competitive analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Search query to analyze"},
                    "location_code": {"type": "integer", "default": 2840},
                    "language_code": {"type": "string", "default": "en"},
                    "depth": {"type": "integer", "default": 10},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "serp_ai_mode",
            "description": "Analyze AI mode search results for a keyword: check if AI overview exists and which URLs are cited by AI systems.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "location_code": {"type": "integer", "default": 2840},
                    "language_code": {"type": "string", "default": "en"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keyword_difficulty",
            "description": "Get keyword difficulty scores for a list of keywords (0-100 scale).",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "location_code": {"type": "integer", "default": 2840},
                    "language_code": {"type": "string", "default": "en"},
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "historical_search_volume",
            "description": "Get 12-month historical search volume trends for keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "location_code": {"type": "integer", "default": 2840},
                    "language_code": {"type": "string", "default": "en"},
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "competitors_domain",
            "description": "Find competing domains for a given domain — domains that rank for similar keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Target domain (e.g., 'example.com')"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "domain_intersection",
            "description": "Find keywords that two domains both rank for — useful for competitive gap analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain1": {"type": "string"},
                    "domain2": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["domain1", "domain2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keywords_for_site",
            "description": "Get keywords that a specific site ranks for, with position, traffic estimates, and difficulty.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Domain or URL to analyze"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["url"],
            },
        },
    },
    # --- Fallback & Monitoring ---
    {
        "type": "function",
        "function": {
            "name": "execute_with_fallback",
            "description": "Retry a failed tool call with automatic fallback to an alternative tool. Use when a primary tool returns an error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the failed tool"},
                    "tool_args": {"type": "object", "description": "Original arguments passed to the failed tool"},
                    "original_error": {"type": "string", "default": "", "description": "Error message from the failure"},
                },
                "required": ["tool_name", "tool_args"],
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
    "ai_mentions": ai_mentions,
    # Composable audit suite
    "audit_crawlability": audit_crawlability,
    "audit_meta_tags": audit_meta_tags,
    "audit_structured_data": audit_structured_data,
    "audit_performance": audit_performance,
    "audit_mobile": audit_mobile,
    "audit_i18n": audit_i18n,
    "audit_content": audit_content,
    "render_and_compare": render_and_compare,
    # Research & analysis
    "validate_sitemap": validate_sitemap,
    "check_redirects": check_redirects,
    "internal_link_audit": internal_link_audit,
    "duplicate_content_scan": duplicate_content_scan,
    "hreflang_validator": hreflang_validator,
    "content_quality_assessment": content_quality_assessment,
    "content_freshness_scan": content_freshness_scan,
    "pagination_audit": pagination_audit,
    "validate_clusters": validate_clusters,
    "submit_deliverable": submit_deliverable,
    "select_clusters": select_clusters,
    "list_clusters_all": list_clusters_all,
    "promote_cluster": promote_cluster,
    "discard_cluster": discard_cluster,
    "propose_cluster": propose_cluster,
    # Exposed DataForSEO
    "serp_organic": serp_organic,
    "serp_ai_mode": serp_ai_mode,
    "keyword_difficulty": keyword_difficulty,
    "historical_search_volume": historical_search_volume,
    "competitors_domain": competitors_domain,
    "domain_intersection": domain_intersection,
    "keywords_for_site": keywords_for_site,
    # Fallback chains
    "execute_with_fallback": execute_with_fallback,
}

# Tool categories for selective loading (reduces context window usage)
# Based on Anthropic's ACI framework — only expose relevant tools per task
TOOL_CATEGORIES = {
    "audit": [
        "technical_seo_audit", "audit_crawlability", "audit_meta_tags",
        "audit_structured_data", "audit_performance", "audit_mobile",
        "audit_i18n", "audit_content", "render_and_compare",
        "validate_sitemap", "check_redirects", "internal_link_audit",
        "duplicate_content_scan", "hreflang_validator", "content_freshness_scan",
        "pagination_audit",
    ],
    "content": [
        "generate_draft", "preflight_draft", "seo_linter", "geo_scorer",
        "content_quality_assessment",
    ],
    "research": [
        "extract_seeds", "pull_universe", "cluster_keywords", "validate_clusters",
        "score_clusters", "select_clusters", "list_clusters_all", "promote_cluster",
        "discard_cluster", "propose_cluster",
        "recommend_pillars", "serp_organic", "serp_ai_mode",
        "keyword_difficulty", "historical_search_volume", "competitors_domain",
        "domain_intersection", "keywords_for_site", "web_search",
        "submit_deliverable",
    ],
    "strategy": [
        "plan_calendar", "run_discovery", "submit_deliverable",
    ],
    "gsc": [
        "gsc_performance", "gsc_inspect_url", "gsc_list_sitemaps",
        "gsc_list_sites", "gsc_submit_sitemap",
    ],
    "indexing": [
        "submit_indexnow", "submit_single_url", "bing_submit_url",
    ],
    "monitoring": [
        "ai_mentions",
    ],
    "memory": [
        "read_memory", "record_fact", "record_learning", "record_decision",
        "record_artefact", "draft_run_summary",
    ],
    "meta": [
        "log_conversation", "suggest_improvements", "execute_with_fallback",
    ],
}

# Intent classification keywords — map user phrases to tool categories
INTENT_KEYWORDS = {
    "audit": ["audit", "check", "analyze", "review", "scan", "inspect", "test", "validate", "crawl", "robots", "sitemap", "redirect", "hreflang", "duplicate"],
    "content": ["write", "draft", "article", "content", "blog", "lint", "score", "preflight", "quality"],
    "research": ["keyword", "research", "competitor", "SERP", "search volume", "difficulty", "trend", "seed", "cluster", "universe"],
    "strategy": ["plan", "calendar", "strategy", "discover", "intake", "onboard"],
    "gsc": ["google search console", "GSC", "performance", "impressions", "clicks", "CTR", "indexing status"],
    "indexing": ["index", "submit", "IndexNow", "Bing", "crawl request"],
    "monitoring": ["mention", "AI citation", "visibility", "monitor", "track"],
}


def select_tools_for_intent(user_message: str, always_include: list[str] | None = None) -> list[dict]:
    """Select relevant tool definitions based on user intent.
    
    Classifies the user's message into categories and returns only the
    tool definitions for those categories, reducing context window usage.
    
    Args:
        user_message: The user's request
        always_include: Additional tool names to always include (e.g., memory tools)
    
    Returns:
        Filtered list of tool definitions
    """
    user_lower = user_message.lower()
    selected_categories = set()
    
    # Classify intent based on keywords
    for category, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in user_lower:
                selected_categories.add(category)
                break
    
    # If no categories matched, include all (fallback to full context)
    if not selected_categories:
        return TOOL_DEFINITIONS
    
    # Always include memory tools (needed for context in every interaction)
    selected_categories.add("memory")
    
    # Collect tool names from selected categories
    selected_tool_names = set()
    for category in selected_categories:
        selected_tool_names.update(TOOL_CATEGORIES.get(category, []))
    
    # Add always_include tools
    if always_include:
        selected_tool_names.update(always_include)
    
    # Filter TOOL_DEFINITIONS to only include selected tools
    filtered = [td for td in TOOL_DEFINITIONS if td["function"]["name"] in selected_tool_names]
    
    return filtered


def run_agent(
    user_message: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
    max_rounds: int = 20,
    stop_check=None,
) -> dict[str, Any]:
    """Run the SEO agent with function calling loop.

    stop_check: optional callable that raises StopRequested when the user
    has asked to stop; checked before every LLM round and before the
    post-loop tail so a stopped run doesn't burn more calls.
    """
    sid = session_id or session_store.new_session_id()
    session_data: dict[str, Any] = {
        "session_id": sid,
        "messages": [],
        "tool_results": [],
        "artifacts": {},
    }

    # Load skills applicable to this agent
    skills_content = memory.load_skills(AGENT_NAME)
    skills_context = ""
    if skills_content:
        skills_context = f"\n\nSkills:\n\n{skills_content}"

    system = SYSTEM_PROMPT + skills_context
    if context:
        system += f"\n\nCurrent session context:\n{llm.format_json(context)}"

    messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]
    
    # Select tools based on intent (reduces context window usage)
    # If intent is ambiguous, falls back to full tool set
    tools_for_session = select_tools_for_intent(user_message)

    for round_num in range(max_rounds):
        if stop_check is not None:
            stop_check()

        resp = llm.chat(messages, system=system, tools=tools_for_session, temperature=0.3)

        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])

        if content:
            messages.append({"role": "assistant", "content": content})
            session_data["messages"].append({"role": "assistant", "content": content})
            print(f"\n[Agent]: {content[:200]}...")

        if not tool_calls:
            break

        # Execute tool calls in parallel if multiple
        if len(tool_calls) > 1:
            print(f"\n[Parallel execution]: Running {len(tool_calls)} tools concurrently...")
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def execute_tool(tc):
                tool_name = tc["name"]
                tool_args = tc["arguments"]
                print(f"\n[Tool call]: {tool_name}({tool_args[:100] if isinstance(tool_args, str) else '...'}...)")

                parsed_args, parse_error = llm.safe_parse_tool_args(tool_args)
                if parse_error is not None:
                    print(f"[Tool args parse error]: {tool_name}: {parse_error}")
                    return {
                        "tc": tc,
                        "result": None,
                        "parsed_args": {},
                        "result_str": json.dumps({
                            "error": f"Your tool arguments could not be parsed as JSON: {parse_error} "
                                     "Re-send the tool call with valid JSON arguments."
                        }),
                        "error": f"argument parse error: {parse_error}",
                        "success": False,
                    }

                try:
                    result = TOOL_CALLABLES[tool_name](**parsed_args)
                    result_str = llm.format_json(result)
                    return {
                        "tc": tc,
                        "result": result,
                        "parsed_args": parsed_args,
                        "result_str": result_str,
                        "error": None,
                        "success": True,
                    }
                except Exception as e:
                    print(f"[Tool error]: {tool_name}: {e}")
                    return {
                        "tc": tc,
                        "result": None,
                        "parsed_args": parsed_args,
                        "result_str": json.dumps({"error": str(e)}),
                        "error": str(e),
                        "success": False,
                    }
            
            # Execute all tools in parallel
            with ThreadPoolExecutor(max_workers=min(len(tool_calls), 8)) as executor:
                futures = {executor.submit(execute_tool, tc): tc for tc in tool_calls}
                results = [future.result() for future in as_completed(futures)]

            # Add ONE assistant message with ALL tool_calls (OpenAI format requirement)
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
                    for tc in tool_calls
                ],
            })

            # Add all tool results (in completion order for faster feedback)
            for res in results:
                tc = res["tc"]
                session_data["tool_results"].append({
                    "round": round_num,
                    "tool": tc["name"],
                    "args": tc["arguments"],
                    "result": res["result"],
                    "success": res["success"],
                    "error": res["error"],
                })
                pipeline_recorder.record_tool(
                    tc["name"],
                    res["parsed_args"],
                    res["result"],
                    res["success"],
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": res["result_str"][:4000],
                })
        else:
            # Single tool call - execute sequentially
            tc = tool_calls[0]
            tool_name = tc["name"]
            tool_args = tc["arguments"]

            print(f"\n[Tool call]: {tool_name}({tool_args[:100] if isinstance(tool_args, str) else '...'}...)")

            parsed_args, parse_error = llm.safe_parse_tool_args(tool_args)
            if parse_error is not None:
                print(f"[Tool args parse error]: {tool_name}: {parse_error}")
                result_str = json.dumps({
                    "error": f"Your tool arguments could not be parsed as JSON: {parse_error} "
                             "Re-send the tool call with valid JSON arguments."
                })
                session_data["tool_results"].append({
                    "round": round_num,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": None,
                    "success": False,
                    "error": f"argument parse error: {parse_error}",
                })
            else:
                try:
                    result = TOOL_CALLABLES[tool_name](**parsed_args)
                    result_str = llm.format_json(result)
                    session_data["tool_results"].append({
                        "round": round_num,
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                        "success": True,
                        "error": None,
                    })
                    pipeline_recorder.record_tool(tool_name, parsed_args, result, True)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    print(f"[Tool error]: {e}")
                    session_data["tool_results"].append({
                        "round": round_num,
                        "tool": tool_name,
                        "args": tool_args,
                        "result": None,
                        "success": False,
                        "error": str(e),
                    })
                    pipeline_recorder.record_tool(tool_name, parsed_args, None, False)

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str[:4000],
            })

    # Post-loop synthesis: if agent stopped with planning text but no final report, force synthesis
    if stop_check is not None:
        # User asked to stop — skip the expensive post-loop tail entirely
        stop_check()

    if session_data["tool_results"]:
        last_assistant = next(
            (m for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")),
            None
        )
        
        # Check if last message is planning text (mentions future actions but no tool calls)
        needs_synthesis = False
        if last_assistant:
            content = last_assistant["content"].lower()
            planning_indicators = ["let me", "now let's", "next i'll", "let's check", "let's validate", "i'll now"]
            has_planning = any(indicator in content for indicator in planning_indicators)
            has_findings = any(keyword in content for keyword in ["finding", "result", "issue", "problem", "recommendation", "summary"])
            needs_synthesis = has_planning and not has_findings
        
        if needs_synthesis:
            print("\n[Post-Loop Synthesis] Agent stopped with planning text, forcing final report...")
            
            # Build condensed message history for synthesis to avoid context overflow
            # Keep: system context, original user message, last assistant message, and condensed tool results
            condensed_messages = []
            
            # Add original user message
            for msg in messages:
                if msg.get("role") == "user" and "audit" in msg.get("content", "").lower():
                    condensed_messages.append(msg)
                    break
            
            # Condense tool results into a summary
            tool_summary_parts = []
            for tr in session_data["tool_results"]:
                tool_name = tr["tool"]
                result = tr["result"]
                if isinstance(result, dict):
                    # Extract key findings from audit tools
                    if "checks" in result:
                        checks = result["checks"]
                        issues = [c for c in checks if c.get("status") in ["fail", "warn"]]
                        if issues:
                            tool_summary_parts.append(f"**{tool_name}**: {len(issues)} issues found")
                            for issue in issues[:5]:  # Top 5 issues per tool
                                tool_summary_parts.append(f"  - {issue.get('check_name', 'Unknown')}: {issue.get('message', '')[:100]}")
                    elif "score" in result:
                        tool_summary_parts.append(f"**{tool_name}**: Score {result['score']}/100")
                    else:
                        # Generic summary for other tools
                        result_str = json.dumps(result)[:200]
                        tool_summary_parts.append(f"**{tool_name}**: {result_str}")
            
            tool_summary = "\n".join(tool_summary_parts) if tool_summary_parts else "No detailed results available"
            
            # Add last assistant message for context
            if last_assistant:
                condensed_messages.append(last_assistant)
            
            # Add condensed tool results
            condensed_messages.append({
                "role": "user",
                "content": f"Here are the condensed results from your audit tools:\n\n{tool_summary}"
            })
            
            synthesis_prompt = """Based on the audit results above, produce a STRUCTURED FINAL REPORT with these sections:

## Executive Summary
2-3 sentences: overall health assessment, number of critical issues found

## Critical Issues (must fix immediately)
- List each critical issue with the tool that found it
- Explain why it's critical and what the impact is

## Warnings (should fix soon)
- List each warning with the tool that found it
- Brief explanation of the issue

## Opportunities (nice to have improvements)
- List optimization opportunities

## Technical Details
- Pages analyzed
- Tools used and their results
- Key metrics (scores, counts)

## Recommended Next Steps
- Prioritized action items (1-5 items)
- Be specific about what to fix and why

Use the actual data from the tool results. Be specific and cite findings. This report will be presented to the user."""

            condensed_messages.append({"role": "user", "content": synthesis_prompt})

            # One final LLM call for synthesis with condensed context
            try:
                print(f"  [Synthesis] Using {len(condensed_messages)} condensed messages (vs {len(messages)} full messages)")
                synthesis_resp = llm.chat(
                    condensed_messages,
                    system=system,
                    tools=[],  # No tools - just generate report
                    temperature=0.3,
                )
                synthesis_content = synthesis_resp.get("content", "")
                if synthesis_content:
                    messages.append({"role": "assistant", "content": synthesis_content})
                    session_data["messages"].append({"role": "assistant", "content": synthesis_content})
                    print(f"  [Synthesis] ✓ Generated {len(synthesis_content)} char report")
                    print(f"\n[Agent Final Report]: {synthesis_content[:300]}...")
                else:
                    print("  [Synthesis] ⚠ LLM returned empty response")
            except Exception as e:
                print(f"  [Synthesis] ⚠ Failed: {e}")
                # Fallback: create a basic summary from tool results
                fallback_report = f"""## SEO Audit Summary

**Tools Executed:** {len(session_data["tool_results"])} audit tools

{tool_summary}

### Next Steps
Review the detailed findings above and prioritize fixes based on severity.
"""
                messages.append({"role": "assistant", "content": fallback_report})
                session_data["messages"].append({"role": "assistant", "content": fallback_report})
                print(f"  [Synthesis] Used fallback report instead")

    # Save session
    session_store.save_session(sid, session_data)

    if session_data["tool_results"]:
        tools_used = [t["tool"] for t in session_data["tool_results"]]
        successful = sum(1 for t in session_data["tool_results"] if t.get("success"))
        failed = sum(1 for t in session_data["tool_results"] if not t.get("success"))

        # Finalize run summary — historical record, not findings dump
        tools_summary = ", ".join(sorted(set(tools_used)))
        outcome = f"{len(tools_used)} tool calls ({successful} ok, {failed} failed): {tools_summary}"
        
        # Extract a clean outcome summary using LLM instead of raw message content
        outcome_summary = ""
        try:
            messages_for_summary = session_data.get("messages", [])
            if messages_for_summary:
                summary_prompt = """You are summarizing what was accomplished in this SEO agent session. 
Look at the conversation and extract ONLY the final outcome/result delivered to the user.
Be concise (max 200 chars). Focus on what was found/achieved, not the process.
If the agent delivered a report, summary, or recommendation, capture the key finding.
Do NOT include intermediate thinking or planning steps."""
                
                summary_messages = [
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": f"Conversation:\n{json.dumps(messages_for_summary[-6:], default=str)}"}
                ]
                
                summary_resp = llm.chat(summary_messages, temperature=0.3)
                if summary_resp.get("content"):
                    outcome_summary = summary_resp["content"][:200].strip()
        except Exception as e:
            print(f"  ⚠ Failed to extract outcome summary: {e}")
        
        memory.finalize_run_summary(
            goal=user_message[:200],
            did=outcome,
            found=outcome_summary if outcome_summary else "",
            artifacts="see session " + sid,
        )

        # Post-response memory synthesis
        try:
            from .tools.memory_synthesis import synthesize_memories_from_session
            print(f"\n[Memory Synthesis] Extracting learnings from session {sid}...")
            synthesis_result = synthesize_memories_from_session(
                session_id=sid,
                messages=session_data.get("messages", []),
                tool_results=session_data.get("tool_results", []),
            )
            if synthesis_result.get("status") == "success":
                print(f"  ✓ Extracted {synthesis_result.get('facts_count', 0)} facts")
                print(f"  ✓ Extracted {synthesis_result.get('learnings_count', 0)} learnings")
                print(f"  ✓ Extracted {synthesis_result.get('decisions_count', 0)} decisions")
        except Exception as e:
            print(f"  ⚠ Memory synthesis failed: {e}")

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

        # Auto-trigger self-learning loop
        try:
            from .tools.self_learning import run_self_learning
            print(f"\n[Self-Learning] Analyzing session {sid}...")
            result = run_self_learning(sid)
            if result.get("status") == "success":
                print(f"  ✓ Proposed {result.get('improvements_proposed', 0)} improvements")
                print(f"  ✓ Added {result.get('missing_memories_added', 0)} missing memories")
                print(f"  ✓ Stored {result.get('proposals_stored', 0)} proposal files")
                print("  → Run 'python -m src.improvements' to review proposals")
        except Exception as e:
            print(f"  [WARN] Self-learning failed: {e}")  # Non-fatal

    return session_data


def run_agent_turn(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    max_tool_rounds: int = 20,
) -> tuple[list[dict[str, str]], list[dict]]:
    """Process one conversation turn with the agent.
    
    Takes the existing message history, sends it to the LLM with tools,
    executes any tool calls, and returns the updated message history and tool results.
    
    Args:
        messages: Current conversation history (will be extended in-place)
        system: System prompt (if None, uses default SYSTEM_PROMPT)
        max_tool_rounds: Maximum number of tool call rounds per turn
        
    Returns:
        Tuple of (updated messages list, list of tool results from this turn)
    """
    if system is None:
        system = SYSTEM_PROMPT
    
    tool_results = []
    
    for round_num in range(max_tool_rounds):
        # Call LLM with current messages
        response = llm.chat(messages, system=system, tools=TOOL_DEFINITIONS, temperature=0.3)
        
        # Add assistant response to messages
        assistant_msg = {"role": "assistant", "content": response.get("content", "")}
        messages.append(assistant_msg)
        
        # Check for tool calls
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            break

        # Execute each tool call and collect results
        tool_results_this_round = []
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args_str = tool_call["function"]["arguments"]

            try:
                tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
            except json.JSONDecodeError:
                tool_args = {}

            print(f"\n[Tool call]: {tool_name}({json.dumps(tool_args)[:100]}...)")

            try:
                result = TOOL_CALLABLES[tool_name](**tool_args)
                result_str = json.dumps(result)[:4000]  # Truncate for context window
                tool_results.append({
                    "round": round_num,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                })
            except Exception as e:
                result_str = json.dumps({"error": str(e)})
                print(f"[Tool error]: {e}")

            tool_results_this_round.append((tool_call, result_str))

        # Add ONE assistant message with ALL tool_calls (OpenAI format)
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {
                        "name": tool_call["function"]["name"],
                        "arguments": tool_call["function"]["arguments"]
                    }
                }
                for tool_call, _ in tool_results_this_round
            ],
        })

        # Add individual tool result messages
        for tool_call, result_str in tool_results_this_round:
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result_str,
            })
    
    return messages, tool_results
