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
- [x] Thin-market resilience (4baba5d): `pull_universe` keeps the discovery seeds as a floor, and when direct expansion is
      thin (<15 keywords) escalates to competitor discovery (`serp_organic` → top domains → `keywords_for_site`) so a
      strategy can always be built; pipeline logs a thin-market note instead of aborting; agent prompt notes zero/low
      volumes are not a failure. Fixed `keywords_for_site` parser (volume/difficulty/rank were read from wrong paths,
      always 0) and dropped the trends call whose endpoint 404s; added `budget_remaining()` for budget-aware fallbacks.
      VERIFIED 2026-09-01: BG thin-market E2E — seeds floor returns 58 keywords for "моноспектакъл"; forced-thin path
      discovers competitors via SERP and adds 100 competitor keywords (57→157); keywords_for_site returns real volumes.

## Verification (I test end-to-end myself)
- [x] Unit: parse helper vs malformed samples; budget cap with low test cap — PASS 2026-08-31, re-PASS since
- [x] Local E2E (browser, headless Chrome + CDP): live activity feed + stage chips stream mid-run in chat and RunView
      ("Live activity" card) — PASS 2026-09-01 (3 runs, no console errors)
- [x] Local E2E: enforced-graph driver `run_keyword_strategy` streams its nodes live (extract seeds ✓ → keyword universe ✓
      → cluster …) and records seeds/intake/keywords stages as they happen — PASS 2026-09-01
- [x] Local E2E: stop mid-run — `POST /api/chat/stop` flips the run to `stopped` within ~2-3 s (instant abandon, no waiting
      for the in-flight LLM call) — PASS 2026-09-01 on 882a3cb
- [x] Local E2E: DFS language resolution up front — BG market resolves to `bg` before any research call; intake shows
      "Locale #2100 / bg, Market BG-BG"; zero wasted location/language pairing calls — PASS 2026-09-01
- [!] Local E2E: full graph to the tail (validate → score → select → citability → pillars) BLOCKED locally — the token-plan
      provider holds the large clustering LLM call past the 120 s timeout even with 20 s pacing (5/5 attempts stalled on
      2026-09-01). Hardened in f943a30 (payload trimmed + bounded retry); production uses the cloud API which does not queue.
- [x] Unit (offline, stubbed LLM): cluster payload trim (top-80 by volume, one-sentence rationale, max_tokens 4500) +
      `_cluster_with_retry` bounded at 2 calls — PASS 2026-09-01
- [ ] Production: push → Railway auto-deploys → run compact strategy on Vercel URL, poll /api/runs + /activity, confirm full
      graph + orphaned-run sweep (in progress)

## Decisions log
- 2026-08-31: Chat-confirm for optional steps (no quick-reply buttons) — user confirmed original flow.
- 2026-08-31: Budget = report progress + ask permission to continue (user).
- 2026-08-31: Technical SEO audit on-demand only; deterministic tools only; artifact queryable via WebMCP + RunView (user).
- 2026-08-31: No knowledge graph for cluster governance — artifact CRUD + scoped re-seed suffices for the deadline (revisit post-hackathon).
- 2026-08-31: Per-keyword difficulty/volume/intent/CPC = zero extra cost (already in keyword_suggestions responses) — surface only.
- 2026-08-31: AI-citability folded in as headline stage on top of existing pipeline, not a replacement.
- 2026-09-01: Strategy pipeline enforced as a code graph (`run_keyword_strategy` driver, 84d83c9): deterministic node order
  seeds → universe → cluster → validate gate → score → select → citability → pillars. LLM fills content per node; the graph
  enforces order and mandatory gates. Reason: free-form agent loops skipped validate/discard-reason steps.
- 2026-09-01: Stop = instant abandon (be141f2): stop flag is checked inside streaming iteration, run closes as `stopped`
  immediately — no waiting for the in-flight LLM call to finish.
- 2026-09-01: LLM pacing (ae8cbb6): `LLM_MIN_INTERVAL_SECONDS` enforces a floor between LLM calls; local `.env` = 20s
  (token-plan provider queues bursts), production leaves it unset (0).
- 2026-09-01: DFS market → language resolved up front from `locations_and_languages`, cached process-wide (882a3cb), and
  rejected location/language pairs memoized (3de62d2). Reason: BG market calls wasted budget on wrong pairings; the phantom
  `keyword_difficulty` endpoint does not exist (924e131) — difficulty comes from keyword stats already in responses.
- 2026-09-01: Cluster-node hardening (f943a30): clustering is the largest LLM call in the graph, so rank keywords by volume
  and cap at 80, one-sentence rationales, cap completion at 4500 tokens, and one bounded node-level retry before failing
  fast. Reason: queued/slow endpoints held the large prompt+completion past the 120 s timeout, aborting the graph and
  forcing the outer agent to re-run seeds + universe (re-billing DataForSEO).
- 2026-09-01: Thin markets get a fallback ladder, not an abort (4baba5d, user direction): some languages/niches have few or
  no search terms (user's case — "изречена поезия" in Bulgarian returned nothing, so "моноспектакъл" from the discovery
  input carried the strategy). pull_universe therefore (1) caps direct seed expansion to 5 seeds, (2) always keeps the seeds
  themselves as a floor, and (3) escalates to competitor discovery (SERP → top domains → ranked keywords) when expansion is
  thin. Low/zero volumes in a thin run are reported as "competitor/thematic evidence", never back-filled with invented data.
- 2026-09-01: Seeds must stay in the market's own language (94a8cf3): first prod thin-market run (chat-20260901T070533) built
  a strategy from 8 seed-only keywords — but extract_seeds had transliterated "моноспектакъл" into "Bulgarian monospectacle
  poet", so expansion + competitor discovery had no in-market term to latch onto. extract_seeds now preserves verbatim native
  terms and seeds in the target search language (language_code passed from the pipeline). Verified: BG brief now yields
  "моноспектакъл"/"изречена поезия" verbatim, which expand to ~58 keywords.
- 2026-09-01: Cluster selection is gated on relevance to the business, not volume (aea1030, user request): the thin-market
  poetry re-run (chat-20260901T071832) selected high-volume OFF-TOPIC clusters (Chitanka e-books, literature curriculum,
  folklore) and discarded the on-topic "Bulgarian Poetry Performance & Spoken Word" cluster, because select_clusters ranked
  by opportunity and never saw the business description. Relevance to the business is now the hard gate (business_description
  threaded from the pipeline); off-topic volume is explicitly rejected and never padded in, and in thin markets a low-volume
  tightly-relevant cluster beats a high-volume irrelevant one. Verified: the poetry scenario now selects the low-volume poetry
  cluster and discards the three off-topic ones with concrete "off-topic" reasons. Discarded clusters remain visible/reversible.

## Learnings (append as discovered)
- Token-plan provider queues BURST traffic: isolated probes return in seconds, but 4+ rapid agent calls get held open with
  keep-alive pings for 10+ minutes (defeats the 120s read timeout). Fix: pace calls (see decision above).
- Worker threads do not inherit contextvars — parallel tool dispatch attributed runs/DFS budgets to the wrong run until the
  context was copied into the thread (be141f2).
- DataForSEO language support is market-bound: the BG market only serves Bulgarian keywords. A BG run legitimately yields
  Bulgarian keywords; the agent should note the language mix in its answer rather than "fix" it.
- Pacing alone does not protect LARGE LLM calls on a queued endpoint: with 20 s pacing the small calls (seeds, orchestrator
  rounds) passed but the big clustering call stalled 5/5 times on 2026-09-01. Shrink the payload (fewer keywords, shorter
  rationale, capped completion) in addition to pacing.
- Two local backends sharing one runs dir + one LLM key is a trap: the browser E2E silently hit the OTHER backend (:8001),
  so its in-memory activity was invisible from :8000 and the run tested stale code. Always confirm `POST /api/chat/stream`
  landed in the backend under test before trusting an E2E.
- DFS labs response shapes differ per endpoint and are easy to parse silently to zeros: `ranked_keywords` nests volume under
  `keyword_data.keyword_info.search_volume` and rank/difficulty under `ranked_serp_element` (no top-level `search_volume`,
  no `impressions_info`), and an invalid `order_by`/`filters` field returns 40501 Invalid Field rather than ignoring it.
  Always dump one raw item before trusting a parser.
- Don't assume a DataForSEO endpoint exists because its name sounds right: `/v3/keywords_data/trends/trending_keywords/live`
  404s (there is no trending-keywords endpoint) yet the wrapper burned one budgeted call per run before being disabled.
- Some markets/niches have little or no keyword data by nature, not by bug — build fallbacks (competitor ranked keywords +
  the discovery seeds themselves) instead of treating an empty universe as a failure.
