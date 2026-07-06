# SEO Agent Tools Reference

## Content Strategy Workflow (6 tools)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `extract_seeds` | Extract keyword seeds from business description | `business_description` |
| `pull_universe` | Expand seeds into keyword universe via DataForSEO | `seeds` |
| `cluster_keywords` | Cluster keywords into thematic groups | `keywords` |
| `score_clusters` | Score clusters for SEO + GEO opportunity | `clusters` |
| `recommend_pillars` | Select best clusters as content pillars | `scored_clusters` |
| `plan_calendar` | Create content calendar from pillars | `pillars` |

## Content Creation (4 tools)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `generate_draft` | Generate article draft for a calendar item | `article_title`, `primary_keyword` |
| `preflight_draft` | Pre-flight review of article draft | `draft` |
| `seo_linter` | Lint article for on-page SEO | `article` |
| `geo_scorer` | Score article for AI citation potential | `article` |

## Technical & Audit (1 tool)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `technical_seo_audit` | Run 24-check technical SEO audit | `url` |

## External Integrations (9 tools)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `submit_indexnow` | Submit URLs to IndexNow for faster indexing | `urls`, `key` |
| `bing_submit_url` | Submit URL to Bing for indexing | `site_url`, `page_url` |
| `get_site_keywords` | Get top keywords from Bing Webmaster Tools | `site_url` |
| `web_search` | Search the web for current information | `query` |
| `gsc_performance` | Get GSC performance data | `site_url` |
| `gsc_submit_sitemap` | Submit sitemap to Google Search Console | `site_url`, `sitemap_url` |
| `gsc_list_sitemaps` | List sitemaps in GSC | `site_url` |
| `gsc_inspect_url` | Inspect URL indexing status in GSC | `site_url`, `inspection_url` |
| `gsc_list_sites` | List all sites in GSC account | (none) |

## Discovery (1 tool)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `run_discovery` | Interactive business intake conversation | `conversation_history` (optional) |

## Memory (8 tools)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `read_memory` | Read facts/learnings/decisions/tasks from blackboard | `memory_type` (optional) |
| `record_fact` | Record an observed truth | `fact` |
| `record_learning` | Record a concluded rule or pattern | `learning` |
| `record_decision` | Record a choice made and why | `decision` |
| `post_task` | Post a task to the blackboard | `task_goal` |
| `complete_task` | Mark a task as completed | `task_goal` |
| `record_artefact` | Record a durable deliverable | `name`, `summary`, `location` |
| `draft_run_summary` | Draft a run summary (mid-run) | `goal`, `did` |

## Self-Improvement (2 tools)

| Tool | Description | Required Inputs |
|------|-------------|----------------|
| `log_conversation` | Log conversation to Braintrust for tracing | `session_id`, `messages`, `tool_results` |
| `suggest_improvements` | Analyze a run and suggest improvements | `session_id`, `conversation_summary` |

**Total: 31 tools**
