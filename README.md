# SEOstrich — **GET FOUND**

**Submission to [The WebMCP Challenge](https://webmcp.devpost.com)** · Submission period Aug 25 – Sep 3, 2026, 1pm PT

An SEO strategy agent whose every decision is on the page as a WebMCP tool, so
the visitor's *own* assistant can read the working, argue with it, and change
the outcome. It builds keyword strategies and AI-visibility (GEO) briefs from
measured DataForSEO data — never a number a model made up — and exposes
**20 tools** on `document.modelContext` to read, audit, edit and reset them.

- **Live app:** https://agent-memory-virid.vercel.app/ — credentials are on the submission form
- **The tools, explained:** open the app and press **WebMCP** in the header (lists all 20 from the live registry, with twelve worked prompts)
- **Registration code:** [`seo-agent/ui/lib/webmcp.ts`](seo-agent/ui/lib/webmcp.ts)
- **Backend API:** https://agent-memory-production-7d5d.up.railway.app
- **Licence:** MIT (see [LICENSE](LICENSE))

## Try WebMCP in 60 seconds

1. Open the live app in **Google Chrome** with `chrome://flags/#enable-webmcp-testing` set to *Enabled* (relaunch), or in **ChatGPT's in-app browser** (works natively). Sign in.
2. Open the pinned **Product Pirates Club** report.
3. Ask your assistant: *"Audit this SEO strategy for me — do the discard reasons actually hold up?"*
4. Then: *"Drop the courses cluster, we don't sell courses, and bring back the one on building AI products."* Watch the report change.
5. Then: *"Reset it to as-produced."* — hands it back clean for the next person, history kept.

`seo_check_if_edited` tells an assistant whether it is looking at the pipeline's own verdict or somebody's edit; that is the whole point of the governance layer.

## Hackathon eligibility — what we started with vs. what we built during the Submission Period

This is a **pre-existing project that was meaningfully extended using WebMCP after the Submission Period start date** (Aug 25, 2026, 11am PT). Per the rules, only work added during the Submission Period should be evaluated. Every commit below is timestamped and verifiable in the git history (`git log --date=iso`).

### Baseline — the project state BEFORE the Submission Period

**Commit [`f9b3f10`](https://github.com/neobozrim/seostrich/tree/f9b3f10) (2026-07-06) is the last commit before the Submission Period began.** Browse the pre-existing project at that tag: https://github.com/neobozrim/seostrich/tree/f9b3f10

At `f9b3f10`, the project contained:

- A CLI-based SEO agent (Python, Qwen function-calling) with 31 tools: DataForSEO keyword research, a content-strategy pipeline (seeds → keywords → clusters → validation → scoring → pillars → calendar → drafts), a 24-check technical SEO audit, GEO/AI-citation scoring, Google Search Console and Bing Webmaster Tools integrations
- The blackboard-style shared agent memory system (`agent-memory/`)
- Braintrust trace logging and a self-improvement loop

There was **no web UI, no hosted service, and no WebMCP** at the baseline.

### Work added DURING the Submission Period (Aug 25 – Sep 3, 2026)

Complete diff: [`f9b3f10` → `main`](https://github.com/neobozrim/seostrich/compare/f9b3f10...main)

| Commit | Date (EEST) | Added |
|---|---|---|
| [`d2b4e4e`](https://github.com/neobozrim/seostrich/commit/d2b4e4e) | 2026-08-30 | Multi-agent orchestrator, FastAPI backend, Next.js chat UI (streaming chat, tool-call display, live memory panel) |
| [`49ec857`](https://github.com/neobozrim/seostrich/commit/49ec857), [`8ff9e61`](https://github.com/neobozrim/seostrich/commit/8ff9e61), [`281d15c`](https://github.com/neobozrim/seostrich/commit/281d15c), [`b476fe7`](https://github.com/neobozrim/seostrich/commit/b476fe7) | 2026-08-30 → 31 | Hosting: Railway deployment config, env-driven persistent storage paths, CORS/PORT handling, declared dependencies |
| [`d0bf7d8`](https://github.com/neobozrim/seostrich/commit/d0bf7d8) | 2026-08-31 | Qwen Cloud API key configuration |
| [`6a1ee0b`](https://github.com/neobozrim/seostrich/commit/6a1ee0b) | 2026-08-31 | Shared-account auth: login flow, signed bearer tokens, UI gate |
| [`590e3c7`](https://github.com/neobozrim/seostrich/commit/590e3c7) | 2026-08-31 | Memory response rendering fix |
| [`06bbd14`](https://github.com/neobozrim/seostrich/commit/06bbd14) | 2026-08-31 | **WebMCP tool registration** (`seo-agent/ui/lib/webmcp.ts`), pipeline Run view, consolidated System panel, profile menu |
| [`9af66ec`](https://github.com/neobozrim/seostrich/commit/9af66ec), [`c623428`](https://github.com/neobozrim/seostrich/commit/c623428) | 2026-09-01 | **WebMCP write tools**: promote / discard / propose clusters, stage artifacts, AI-citability, deterministic run analysis — an external agent drives the pipeline, not just reads it |
| [`84d83c9`](https://github.com/neobozrim/seostrich/commit/84d83c9), [`d3f2dc7`](https://github.com/neobozrim/seostrich/commit/d3f2dc7), [`ee27de2`](https://github.com/neobozrim/seostrich/commit/ee27de2) | 2026-09-01 | Strategy pipeline enforced as a code graph; flow registry as the single source of truth for cards, plan, tool allowlist and WebMCP; market confirmed by the user, never inferred |
| [`1b97506`](https://github.com/neobozrim/seostrich/commit/1b97506), [`935c2f8`](https://github.com/neobozrim/seostrich/commit/935c2f8), [`41d7a0a`](https://github.com/neobozrim/seostrich/commit/41d7a0a) | 2026-09-01 | GEO as a real graph: AI search demand, who is cited, displaceability, open share, People-also-ask; `seo_check_ai_citations` for any domain |
| [`d297774`](https://github.com/neobozrim/seostrich/commit/d297774), [`2a53fed`](https://github.com/neobozrim/seostrich/commit/2a53fed), [`85e6f69`](https://github.com/neobozrim/seostrich/commit/85e6f69) | 2026-09-01 | Measured cluster metrics replace model-estimated scores; reasoning on both sides of every cut; SERP-overlap cluster verification |
| [`e957f8d`](https://github.com/neobozrim/seostrich/commit/e957f8d), [`fec78c0`](https://github.com/neobozrim/seostrich/commit/fec78c0), [`c7e5e40`](https://github.com/neobozrim/seostrich/commit/c7e5e40) | 2026-09-01 | Governance: per-run locking, append-only change history, "edited" badge, reset-to-as-produced, `seo_check_if_edited` / `seo_reset_run` for shared multi-judge use |
| [`01ddb2a`](https://github.com/neobozrim/seostrich/commit/01ddb2a), [`b6066f6`](https://github.com/neobozrim/seostrich/commit/b6066f6), [`419e0c6`](https://github.com/neobozrim/seostrich/commit/419e0c6) | 2026-09-01 | Judge experience: in-app WebMCP guide rendered from the live registry, pinned featured reports on the home canvas, sortable keyword table, mobile layout |

---

## WebMCP implementation

The Next.js frontend registers the SEO pipeline as WebMCP tools using the standard registration pattern, in [`seo-agent/ui/lib/webmcp.ts`](seo-agent/ui/lib/webmcp.ts):

```js
document.modelContext.registerTool({
  name: "seo_get_keyword_clusters",
  title: "SEO keyword clusters",
  description: "List the keyword clusters for the current run with their SEO/GEO/combined scores and member keywords.",
  inputSchema: { type: "object", properties: {} },
  annotations: { readOnlyHint: true },
  execute: async () => { /* fetches the clusters stage of the current pipeline run */ },
}, { signal });
```

Registered tools:

| Tool | Access | Purpose |
|---|---|---|
| `seo_get_pipeline_overview` | read-only | Project, status, and stage list of the current pipeline run |
| `seo_get_keyword_clusters` | read-only | Scored keyword clusters with member keywords |
| `seo_get_content_pillars` | read-only | Prioritized content pillars |
| `seo_get_content_calendar` | read-only | Week-by-week planned content calendar |
| `seo_submit_feedback` | read-write | Attach a review-feedback note to the run for the agent to revise against |
| `seo_restore_defaults` | read-write | Restore the example pipeline run |

**What this enables:** an AI agent running in the browser (ChatGPT's in-app browser, or Chrome with WebMCP enabled) can see the same pipeline artifacts the human sees — read the clusters, explain the strategy, and submit feedback into the agent system's shared memory. Human and agent collaborate on one live analysis instead of copy-pasting between tools.

---

## Repository structure

```
agent-memory/            — blackboard-style shared memory (protocol + entries)
seo-agent/               — the entire multi-agent system:
├── src/                 — orchestrator + SEO/brand/builder/monitoring agents, 40+ tools
├── api/                 — FastAPI backend (chat streaming, memory, runs, artifacts, auth)
├── ui/                  — Next.js chat UI; ui/lib/webmcp.ts = WebMCP registration
├── seed/runs/           — example pipeline run shown in the Run view
└── intake-*.yaml        — example project intake configurations
```

## Run locally

**Backend** (Python):

```bash
cd seo-agent
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env                            # fill in API keys
uvicorn api.main:app --port 8001
```

**Frontend** (Next.js):

```bash
cd seo-agent/ui
npm install
npm run dev                                       # expects NEXT_PUBLIC_API_URL=http://localhost:8001
```

## The agent memory blackboard

The original core of the project: a shared-memory system all agents follow.

- Agents read `agent-memory/PROTOCOL.md` before every run
- Each entry is tagged with the agent name and timestamp
- Old entries are struck through, never deleted (substance preserved in run summaries)
- Agents coordinate via the shared `tasks.md` board
- Artefacts are durable deliverables with rationale and changelog

See `memoryagent-light-buildplan.md` for the original build specification.
