# SEO Agent Hardening + Demo Build — Working Plan

**Created:** 2026-08-31 · **Deadline:** hackathon submission ~Sept 3
**Trigger:** production crash at ~19:23 UTC (chat-20260831T190830) — malformed LLM tool-args JSON hit
unguarded `json.loads` in the chat path. Run stuck `status=running`, UI spinner forever, no Braintrust
trace. Audit also found: `budget_per_job_*` settings wired to nothing, 700-keyword payloads, unbounded
retry encouragement, no stop mechanism, stages only surfaced after completion.

## Status legend
- [ ] todo · [~] in progress · [x] done · [!] blocked/dropped

## Phase 1 — Crash fix (minimal)
- [x] `safe_parse_tool_args()` in `src/llm.py` (json.loads → repair via `extract_json` → `(args|None, error)`)
- [x] Wire into `agent.py` (sequential + parallel paths; parse once, reuse for recorder)
- [x] Wire into `orchestrator.py:395`, `brand_agent.py`, `builder_agent.py`, `monitoring_agent.py`
- [x] Parse failure → error returned to LLM as tool result (self-correct), never kills stream
- [x] `fail_run()` in `pipeline_recorder.py` (status "error" + ended timestamp); `end_run` gains timestamp
- [x] Orchestrator try/finally around `run_agent` — runs always close, `tool_end` always emits
- [x] Startup sweep in `api/main.py`: orphaned "running" runs → "error" (fixes stuck prod run on deploy)
- [x] VERIFIED 2026-08-31: py_compile all files OK; parser unit tests pass (valid/dict/none/trailing-comma/smart-quotes
      repaired; unescaped-quote/junk/list/int → clean errors); crash-path E2E PASS (stream: tool_end(success=False) →
      error → done; run store: status=error + error text + ended timestamp)

## Phase 2 — Cost guardrails (minimal)
- [x] Per-run DFS call counter + cap (default 25, `DFS_MAX_CALLS_PER_RUN`) in `dataforseo._post`
- [x] At cap: raise with progress report (calls by endpoint — no invented dollar prices)
- [x] `continue` flow: extend cap for the session's next run (orchestrator `_CONTINUATION_WORDS`)
- [x] Payload limits: `historical_search_volume` 700→150; `keyword_overview` ≤20
- [x] Prompt: single retry on transient DFS errors only, then report; batching discipline added
- [x] VERIFIED 2026-08-31: compile OK; budget unit test PASS (cap enforced at 3, DFSBudgetExceeded carries
      usage report, continue_dfs_budget 3→28, re-enforced at new cap, None for non-capped runs)

## Phase 3 — Stop + disconnect safety
- [x] Stop flag registry + `POST /api/chat/stop`; `StopRequested` checked between `run_agent` rounds and orchestrator yields
- [x] `api/main.py` watches `request.is_disconnected()` → sets flag
- [x] UI: Send↔Stop toggle + AbortController in `sendMessage`
- [x] UI: error/done events resolve running tool cards (kills forever-spinner)
- [x] VERIFIED 2026-08-31: stop-path E2E PASS (StopRequested mid-run → run closed as "stopped", failed tool_end +
      "Stopped" status + done event, flags cleaned up); `npx tsc --noEmit` clean

## Phase 4 — The demo
- [x] Live stage streaming: `run_agent` in worker thread; orchestrator polls `new_stages` ~1s and yields stage events live
      (contextvars copied into worker so recording + DFS budget keying keep working; GeneratorExit closes run)
      VERIFIED: stream test PASS — stages arrive interleaved BEFORE tool_end; stop/crash/budget suites re-PASS
- [x] Stage model: `STAGE_LABELS` + `record_tool` mappings for audit / competitors / onpage / ai_citability
      (audit checks merged per-tool with `_trim` bounding; competitor sources merged per-tool)
- [x] `submit_deliverable(stage_id, title, artifact)` tool for LLM-synthesized artifacts
      (rejects unknown stages + outside-run; parses string artifacts; recorded via `record_deliverable`;
      wired into TOOL_DEFINITIONS/TOOL_CALLABLES + research/strategy categories; smoke test PASS)
- [x] Cluster governance: over-generate (~8-10) → mandatory `validate_clusters` gate → score → `select_clusters` picks top 3-4 with discard reasons; artifact keeps selected + discarded
      (cluster_keywords default 10 + over-generate prompt; select_clusters LLM tool; recorder `_apply_selection` splits stage)
- [x] Governance ops (chat + WebMCP): list-all, promote, discard, propose-new → scoped re-seed merged into run, others untouched
      (`src/cluster_governance.py` core + `cluster_ops.py` chat tools on active run + REST `/api/runs/{id}/clusters[/promote|/discard|/propose]`
      + `/api/runs/{id}/stages/{stage}`; propose = 1 scoped keyword_suggestions call budget-keyed to the run via `use_run`)
      VERIFIED: governance test PASS (split, promote/discard round-trip, propose stats + budget keying, dup + error paths); all prior suites re-PASS
- [x] Inspector enrichment: per-keyword vol/difficulty/intent/CPC in RunView keywords + cluster members; discarded section
      (recorder stores per-member `keyword_stats` incl. CPC; RunView: KeywordRow/ClusterMember stat chips, KD badge,
      selected-vs-discarded split + collapsible discarded section with reasons, proposed/promoted badges;
      AuditArtifact, CompetitorsArtifact, AiCitabilityArtifact renderers; run StatusBadge + silent refresh + live poll while running)
      VERIFIED: `npx tsc --noEmit` clean; recorder/governance/citability/stream suites re-PASS
- [x] Optional steps: after core run, agent offers on-page + calendar; "yes" continues in same session (state in session_data); technical audit on-demand only (deterministic tools, artifact queryable)
      (system-prompt "Optional steps — confirm, don't assume" + calendar gated on confirmation)
- [x] AI-citability stage (headline): verify DataForSEO AI-optimization docs first; per-keyword search_mentions (AI demand/has-answers/open-share/current cited sources) on selected head terms → PAA free from SERP-advanced → answer-first brief artifact
      (docs verified: target[] accepts keyword entities, items carry question/answer/sources/ai_search_volume;
      new `ai_mentions_keywords` (≤10 terms/call) + `serp_paa` wrappers; deterministic `ai_citability_brief` tool →
      `ai_citability` stage; workflow step 5 makes it part of every strategy run)
      VERIFIED: citability test PASS (assembly, attribution, shares, PAA, stage recording)
- [x] WebMCP additions: seo_get_stage_artifact, seo_list_clusters_all, seo_promote_cluster, seo_discard_cluster, seo_propose_cluster, seo_get_ai_citability
      (+ bonus seo_analyze_run: deterministic health/gap analysis — findings + next steps, zero LLM/DFS — so an
      external agent can inspect what needs fixing; api.ts gained governance/stage REST clients with AbortSignal)
      VERIFIED: `npx tsc --noEmit` clean; FastAPI TestClient integration test PASS (200/404/422 paths + promote/discard/propose)

## Verification (I test end-to-end myself)
- [ ] Unit: parse helper vs malformed samples; budget cap with low test cap
- [ ] Local E2E via browser automation: live chips during run; stop mid-run; crash injection → error status; budget → continue prompt; cluster ops; citability stage; RunView inspection of every stage
- [ ] Production: push → Railway auto-deploys → re-run on Vercel URL, poll /api/runs, confirm orphaned run cleaned

## Decisions log
- 2026-08-31: Chat-confirm for optional steps (no quick-reply buttons) — user confirmed original flow.
- 2026-08-31: Budget = report progress + ask permission to continue (user).
- 2026-08-31: Technical SEO audit on-demand only; deterministic tools only; artifact queryable via WebMCP + RunView (user).
- 2026-08-31: No knowledge graph for cluster governance — artifact CRUD + scoped re-seed suffices for the deadline (revisit post-hackathon).
- 2026-08-31: Per-keyword difficulty/volume/intent/CPC = zero extra cost (already in keyword_suggestions responses) — surface only.
- 2026-08-31: AI-citability folded in as headline stage on top of existing pipeline, not a replacement.

## Learnings (append as discovered)
