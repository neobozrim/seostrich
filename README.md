# SEOstrich — **GET FOUND**

**Submission to [The WebMCP Challenge](https://webmcp.devpost.com)** · Submission period Aug 25 – Sep 3, 2026, 1pm PT

An SEO strategy agent whose every decision is on the page as a WebMCP tool, so
the visitor's *own* assistant can read the working, argue with it, and change
the outcome. It builds keyword strategies and AI-visibility (GEO) briefs from
measured DataForSEO data — never a number a model made up — and exposes
**24 tools** on `document.modelContext` to read, audit, edit and reset them.

- **Live app:** https://www.seostrich.works/ — credentials are on the submission form
- **The tools, explained:** open the app and press **WebMCP** in the header (lists all 24 from the live registry, with twelve worked prompts)
- **Registration code:** [`seo-agent/ui/lib/webmcp.ts`](seo-agent/ui/lib/webmcp.ts)
- **How the pipeline works:** [`seo-agent/docs/graphs.md`](seo-agent/docs/graphs.md) — the system, strategy and GEO graphs, with diagrams
- **Backend API:** https://agent-memory-production-7d5d.up.railway.app
- **Licence:** MIT (see [LICENSE](LICENSE))

## Try WebMCP in 60 seconds

1. Open the live app in **ChatGPT's desktop app** (its in-app browser supports WebMCP out of the box), or in **Google Chrome 149+** with `chrome://flags/#enable-webmcp-testing` set to *Enabled* (relaunch). Sign in.
   - In Chrome, the [Model Context Tool Inspector](https://chromewebstore.google.com/detail/model-context-tool-inspec/gbpdfapgefenggkahomfgkhfehlcenpd) extension lists every tool the page registers, lets you call any of them by hand with its JSON schema, and has a chat that shows which tool an agent picks for a prompt. Handy for checking all 24 without guessing.
2. Open the pinned **Product Pirates Club** report.
3. Ask your assistant: *"Audit this SEO strategy for me — do the discard reasons actually hold up?"*
4. Then: *"Drop the courses cluster, we don't sell courses, and bring back the one on building AI products."* Watch the report change.
5. Then: *"Reset it to as-produced."* — hands it back clean for the next person, history kept.

`seo_check_if_edited` tells an assistant whether it is looking at the pipeline's own verdict or somebody's edit; that is the whole point of the governance layer.

## Why WebMCP here

An SEO strategy is a chain of judgement calls — which market, which keywords
matter, which clusters are worth pursuing, which topics you could realistically
win. Every one of those is a place a human, or their agent, may reasonably
disagree with the machine.

So the pipeline does not just publish results. It publishes **the reasoning
behind each decision**, and the operations to change it. A visiting agent can
read why a cluster was discarded, override that call with its own reason, add a
topic the pipeline never explored, refresh one cluster's data without re-billing
the rest, and hand the report back exactly as produced when it is done. The
human sees the same report change in front of them, with an "edited" badge and
a full history of who changed what.

## The 24 tools

Registered in [`seo-agent/ui/lib/webmcp.ts`](seo-agent/ui/lib/webmcp.ts) with the standard pattern:

```js
document.modelContext.registerTool({
  name: "seo_list_clusters_all",
  title: "SEO clusters with the reasoning behind each decision",
  description: "List BOTH the selected keyword clusters and the discarded ones. Every cluster carries a `reasoning` block ...",
  inputSchema: { type: "object", properties: {} },
  annotations: { readOnlyHint: true },
  execute: async () => { /* fetches the clusters stage of the current run */ },
}, { signal });
```

**Read the strategy**

| Tool | What it returns |
|---|---|
| `seo_get_pipeline_overview` | Start here: the current run, who it is for, its status, every stage it produced |
| `seo_list_flows` | The flows the agent can run end to end, and what each needs before it starts |
| `seo_get_keywords` | Flat keyword table: volume, difficulty, CPC, intent, cluster membership |
| `seo_get_keyword_clusters` | The selected clusters with measured metrics and member keywords |
| `seo_list_clusters_all` | Selected *and* discarded clusters, each with a `reasoning` block for why it was kept or cut |
| `seo_get_content_pillars` | The pillars to actually write, with type and rationale |
| `seo_get_brief` | The SEO strategy brief: the one page a content team acts on, what to build first, in what order, and why |
| `seo_get_content_calendar` | Publishing order from the SEO strategy brief |
| `seo_get_ai_citability` | AI search demand per topic, which sources AI answers cite, how displaceable they are |
| `seo_check_ai_citations` | Which AI answers cite any domain, and for what. Point it at your site or a competitor |
| `seo_get_stage_artifact` | The raw artifact of one stage, unshaped |
| `seo_analyze_run` | Deterministic check for missing stages, errors or early stops before trusting a run |

**Change it**

| Tool | What it does |
|---|---|
| `seo_promote_cluster` | Bring a discarded cluster back, with your reason |
| `seo_discard_cluster` | Drop a cluster, with your reason. Parked, not deleted |
| `seo_propose_cluster` | Add a topic the pipeline never explored. Runs real keyword research on it |
| `seo_rerun_cluster_research` | Refresh one cluster's data without re-running or re-billing the rest |
| `seo_research_competitor` | Put a competitor on the map and pull the keywords it ranks for |
| `seo_research_keyword` | The phrases around one keyword with real volume, difficulty and CPC - read-only, one lookup, nothing on the run changes |
| `seo_regenerate_brief` | Rebuild the SEO strategy brief from the selection as it stands now |
| `seo_submit_feedback` | Leave a note on the run for the human |

**Govern it**

| Tool | What it does |
|---|---|
| `seo_check_if_edited` | Is this the pipeline's own verdict, or has someone edited it since? |
| `seo_get_governance_history` | Every promotion, discard and proposal since the run was produced |
| `seo_reset_run` | Undo every change. History kept |
| `seo_restore_defaults` | Reset the bundled example run to its shipped state |

Tools that spend DataForSEO money say so in their description. Every tool is
documented in the app's **WebMCP** panel from the live registry.

## The flows

**Content strategy** — intake → seeds → keyword universe → competitors →
clusters → validation gate → scoring → selection → pillars → SEO strategy brief.

**AI visibility (GEO)** — measure real AI search demand, check which AI answers
exist and who they cite, grade whether those sites can realistically be
displaced, then harvest the questions people actually ask, only for the topics
that earned it.

Each flow is a code graph, not a prompt: the order and the gates are fixed,
every node records its output as a stage on the run, and the only thing a model
decides is wording and grouping. Diagrams in [`seo-agent/docs/graphs.md`](seo-agent/docs/graphs.md).

## Two principles the code enforces

**The market is never inferred.** A `.bg` domain does not mean the business
targets Bulgaria in Bulgarian. The pipeline refuses to start until the user has
stated the country *and* language.

**Measured, not estimated.** Cluster metrics are computed from the DataForSEO
rows, not guessed by a model. An earlier version asked an LLM for 0-100 "SEO
scores"; it rated a 670-volume cluster above a 4,360-volume one. Numbers now
come from arithmetic, and every input is published so an agent can re-rank on
whichever metric it cares about.

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
| [`1e32b5c`](https://github.com/neobozrim/seostrich/commit/1e32b5c), [`5992886`](https://github.com/neobozrim/seostrich/commit/5992886), [`b5ebf5c`](https://github.com/neobozrim/seostrich/commit/b5ebf5c) | 2026-09-01 → 02 | Pre-submission review (run-id traversal closed, upload cap, honest guide), repo renamed to SEOstrich, bundled reports install themselves when they change |
| [`b8b0cbd`](https://github.com/neobozrim/seostrich/commit/b8b0cbd), [`645bae2`](https://github.com/neobozrim/seostrich/commit/645bae2), [`4194a34`](https://github.com/neobozrim/seostrich/commit/4194a34) | 2026-09-02 | Competitors on every run: ranked keywords per competitor, brand filter, a relevance gate ("is this YOUR topic?"), the "who ranks for what" map with owner tags |
| [`15e853f`](https://github.com/neobozrim/seostrich/commit/15e853f), [`2845060`](https://github.com/neobozrim/seostrich/commit/2845060), [`c5ad588`](https://github.com/neobozrim/seostrich/commit/c5ad588), [`b4ffa20`](https://github.com/neobozrim/seostrich/commit/b4ffa20) | 2026-09-02 | The report is the product: home is your artefacts, one shared header, live artefact that fills in as the graph runs, editable heading, the orchestrator routes and never edits a result |
| [`c22e2bd`](https://github.com/neobozrim/seostrich/commit/c22e2bd), [`d71b4fd`](https://github.com/neobozrim/seostrich/commit/d71b4fd), [`d89a158`](https://github.com/neobozrim/seostrich/commit/d89a158), [`9b33205`](https://github.com/neobozrim/seostrich/commit/9b33205) | 2026-09-02 | The brief as a stage (rebuilt on demand), archive, OpenAI models with thinking control, the user's own pages read for seeds, every URL in the brief used, the three graphs drawn |
| [`f7c366c`](https://github.com/neobozrim/seostrich/commit/f7c366c), [`4d55ef2`](https://github.com/neobozrim/seostrich/commit/4d55ef2), [`e281438`](https://github.com/neobozrim/seostrich/commit/e281438) | 2026-09-02 | Language names accepted at the market gate, no internal error text ever reaches a chat bubble, repo cleaned for launch |
| [`e281438` → `main`](https://github.com/neobozrim/seostrich/compare/e281438...main) | 2026-09-03 | Launch: every question in the brief is one Google shows (People also ask) with who answers it today; the validation gate parks incoherent themes on its own scores; product-led themes are never pillars; every named competitor checked, competitors addable after the run (`seo_research_competitor`, tool 23); GEO reports check the site's own citations; collapsible steps, three type sizes, scroll anchoring, launch animation; 24 tools verified through Chrome's `document.modelContext.executeTool` and an LLM agent loop over them |

---

## Repository structure

```
README.md                — this file
LICENSE                  — MIT
seo-agent/
├── api/                 — FastAPI backend: chat streaming, runs, artifacts, governance, auth
├── src/                 — orchestrator, agents, flow graphs, 40+ tools
├── ui/                  — Next.js app; ui/lib/webmcp.ts registers the 24 WebMCP tools
├── docs/graphs.md       — the system, strategy and GEO graphs, with diagrams
├── seed/runs/           — six bundled reports (Product Pirates + Braintrust, strategy + AI visibility; two specialty-coffee strategies), pinned on the home canvas
├── tests/               — standalone test scripts, one concern each
└── requirements.txt, railway.toml, .python-version, .env.example
```

`agent-memory/` appears at the repo root at runtime: the API writes pipeline
runs there. It is gitignored and never published.

## Run locally

Copy `seo-agent/.env.example` to `.env` **at the repo root** and fill in
DataForSEO credentials and an OpenAI API key. The agents run on GPT-5.6 Sol
for reasoning steps and GPT-5.6 Terra for fast ones; the model ids are in
`src/config.py` and can be overridden in `.env`. Set `USER_NAME` / `PASSWORD` to
require login; leave them unset and the app stays open (fine locally, not in
public).

**Backend** (Python 3.11+):

```bash
cd seo-agent
python -m venv .venv && .venv\Scripts\activate   # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
uvicorn api.main:app --port 8001
```

**Frontend** (Next.js):

```bash
cd seo-agent/ui
npm install
npm run dev                                       # expects NEXT_PUBLIC_API_URL=http://localhost:8001
```

**Tests** are standalone scripts, one concern each. Run any of them from
`seo-agent/`:

```bash
python tests/geo.py
```

Each prints its assertions and exits non-zero on failure.

## Before WebMCP: the agent memory blackboard

The original core of the project was a blackboard-style shared memory that
every agent wrote to: timestamped facts, decisions and learnings, a task board,
and a self-improvement loop that proposed skills from past runs. That layer is
off by default now (`AGENT_MEMORY=off`) because cross-project memory leaked one
client's context into another's run. The design is in git history at the
baseline commit.
