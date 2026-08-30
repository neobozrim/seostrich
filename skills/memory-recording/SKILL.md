---
name: memory-recording
description: Protocol for recording agent memories to the shared blackboard — defines what belongs in each file, quality gates, task lifecycle, and post-run reflection
applies_to: [seo-agent, orchestrator, branding]
source: auto-skill
updated_at: '2026-07-09T00:00:00.000Z'
---

# Memory Recording Protocol

You are an agent writing to a shared blackboard. Every entry you write is read by other agents and future sessions of yourself. Write with that audience in mind.

## Blackboard Files

The blackboard lives at `agent-memory/` and contains these files:

| File | Purpose | Max working lines |
|------|---------|-------------------|
| `facts.md` | Verified truths about the world/domain | 10 |
| `learnings.md` | Patterns from experience that change future behavior | 10 |
| `decisions.md` | Choices made with rationale | 10 |
| `tasks.md` | Work items with lifecycle status | 10 visible |
| `runs-summaries.md` | Historical record of what was asked, planned, and done | unlimited |
| `artefacts-index.md` | Pointers to deliverables created | unlimited |

Older entries are compacted to `memory-archive.md` (facts, learnings, decisions) or `tasks-archive.md` (completed/abandoned tasks).

## Entry Format

Every entry must follow this format:

```
[agent-tag][ISO-8601-datetime] content text
```

- **Agent tag**: `[seo-agent]`, `[orchestrator]`, `[branding]`, etc. Mandatory. Never leave entries unattributed.
- **Datetime**: ISO 8601 to the minute, UTC: `2026-07-08T15:21`. No seconds.
- **Ordering**: Newest entry on top (prepend, not append). The header line (if present) stays first.

## Quality Gates

### facts.md — Verified truths about the world

Record a fact when you discover something about the domain, user, or environment that:
- Persists across sessions (not temporary state)
- Is not derivable from code, config, or documentation
- Another agent or future session would need to know

**✅ Good facts:**
- "CEE AI PM market has almost zero content competition — verified via DataForSEO keyword gap analysis"
- "productpirates.club has no backlinks yet — confirmed via Ahrefs check on 2026-07-05"
- "User's employer is a hosting provider; user is in a 3-month test period"

**❌ Not facts:**
- "Run 20260708T152017 used tools extract_seeds" ← run metadata → goes in runs-summaries
- "Technical SEO audit found 3 issues" ← audit result → goes in artefacts
- "The agent has 22 tools" ← implementation detail → belongs in code/docs

**Test:** Would another agent starting fresh need this information to do its job? If yes → fact. If no → don't record it.

### learnings.md — Patterns that change future behavior

Record a learning when you discover a pattern through experience that:
- Would change how you (or another agent) approach similar work
- Isn't obvious from documentation or code
- Is generalizable beyond the specific session

**✅ Good learnings:**
- "DataForSEO keyword research requires domain in API request; first call for a new domain is slow (15s+) due to cold cache"
- "Qwen Cloud token plan keys use a different base URL than pay-as-you-go keys"
- "Staggering blog post publication dates looks more natural to Google than publishing all on the same date"

**❌ Not learnings:**
- "The technical_seo_audit tool works correctly" ← observation, not a pattern → if anything, a fact
- "Session ran successfully" ← obvious
- "User asked for pillar strategy" ← session-specific detail → runs-summaries

**Test:** If someone else faced the same situation, would this knowledge change what they do? If yes → learning. If it's just an observation → fact.

### decisions.md — Choices with rationale

Record a decision when:
- There were ≥2 viable options and one was chosen
- The rationale isn't obvious from the outcome alone
- Future agents need to understand why something was done a certain way

**✅ Good decisions:**
- "Neighboring pillars (Option B) chosen for productpirates.club and blog.yavorpopov.com to avoid keyword cannibalization and serve different audiences"
- "Astro chosen over WordPress for full control over meta tags, schema, IndexNow"
- "Removed analyze_competitor, compare_strategies, site_scraper tools — competitor analysis handled by web_search"

**❌ Not decisions:**
- "Used extract_seeds tool to get keywords" ← single path, no choice made
- "Created pillar-strategy.md" ← describing what happened, not a choice
- "Read memory before writing" ← protocol requirement, not a decision

**Test:** If someone asked "why did you do X?", would the answer reveal a non-obvious trade-off? If yes → decision. If there was only one path → don't record it.

## Task Lifecycle

Tasks give visibility into work planned, in progress, and recently done.

**Important:** Only the orchestrator records user-facing tasks. The SEO agent does not record tasks — it executes them.

### Status Flow

```
to do → in progress → done
                    → not doing (with reason)
```

### Rules

1. **Check before creating**: Before posting a task, read `tasks.md`. If the same or overlapping task exists, update its status instead of creating a new one.
2. **No duplicates**: The same task must not appear twice. Update the existing line.
3. **Status changes update the line**: When a task moves from `to do` to `in progress`, edit the existing entry. Don't append a new line.
4. **Visibility**: Top 10 active tasks (to do + in progress) are visible in `tasks.md`. Done and not-doing tasks older than the top 10 are compacted to `tasks-archive.md`.

### Entry Format

```
[agent-tag][datetime][status] task description | affects: files/assets touched
```

**Examples:**
```
[orchestrator][2026-07-08T15:00][to do] Research keywords for productpirates.club | affects: pillar-strategy.md
[orchestrator][2026-07-08T15:10][in progress] Research keywords for productpirates.club | affects: pillar-strategy.md
[orchestrator][2026-07-08T15:45][done] Research keywords for productpirates.club | affects: pillar-strategy.md
[orchestrator][2026-07-08T16:00][not doing] Analyze competitor backlinks | reason: DataForSEO backlinks API not available
```

## Run Summaries

A run summary is a **historical reference** of what was asked, how it was planned, how execution went, and the outcome. It is NOT a findings dump.

### Format

```
## [agent-tag][datetime] short goal description | final

**Requested:** What the user asked for (the actual request, paraphrased)
**Planned:** High-level decomposition of the work (2-3 lines)
**Executed:** What was done, key steps taken, tools used
**Outcome:** What was delivered or achieved
**Outstanding:** Next steps and their urgency (or "None")
```

**Example:**
```
## [seo-agent][2026-07-08T15:00] Pillar strategy for productpirates.club + blog.yavorpopov.com | final

**Requested:** User asked for content pillar strategy for productpirates.club and blog.yavorpopov.com
**Planned:** Extract keyword seeds, pull keyword universe, cluster, score, recommend pillars
**Executed:** Used extract_seeds, pull_universe, cluster_keywords, score_clusters, recommend_pillars tools
**Outcome:** Delivered pillar-strategy.md with keyword data, content types, opportunity scores, syndication strategy, content calendars for both sites
**Outstanding:** Validate keyword volumes when DataForSEO credentials are configured (medium urgency)
```

**What NOT to do:**
- Don't write "Found: nothing notable" — if there were no findings, omit the Found line entirely
- Don't dump tool outputs into the summary
- Don't repeat facts/learnings (those are in their own files)

## Artefacts Index

Pointers to deliverables, not the content itself.

```
name | agent | one-line summary | location
```

**Example:**
```
pillar-strategy | seo-agent | Neighboring strategy for productpirates.club + blog.yavorpopov.com (4 pillars each) | outputs/pillar-strategy.md
```

## Superseding Entries

When a fact, learning, or decision is no longer true:

```
[agent-tag][datetime] ~~old content~~ (superseded YYYY-MM-DDThh:mm by agent-tag: reason)
```

- The original text stays, struck through.
- You may supersede another agent's entry (this is the one edit you can make to others' entries).
- On read, treat struck-through entries as inactive.

## Post-Run Reflection Checklist

After every run, before finalizing, ask yourself these four questions explicitly:

1. **Did I discover a truth about the domain that wasn't already in facts.md?**
   - If yes → record as fact (pass quality gate above)
   - If no → skip

2. **Did I find a pattern in how tools, approaches, or processes work that would help next time?**
   - If yes → record as learning (pass quality gate above)
   - If no → skip

3. **Did I choose between options where the rationale isn't obvious?**
   - If yes → record as decision (pass quality gate above)
   - If no → skip

4. **Are any existing memories now wrong or outdated?**
   - If yes → supersede them with the new information
   - If no → skip

If all four answers are "no", that's fine. Don't force entries. Empty reflection is better than garbage.

## Common Anti-Patterns

| Anti-pattern | What to do instead |
|---|---|
| Recording "Run X used tools Y, Z" as a fact | Put tool usage in runs-summaries |
| Recording audit results as facts | Audit results → artefacts (they're deliverables) |
| Creating a new task line for status changes | Update the existing line |
| Writing "Found: nothing notable" in run summary | Omit the Found line entirely |
| Recording every observation as a learning | Learnings must change future behavior; observations are facts |
| Recording single-path actions as decisions | Decisions require ≥2 options with a choice |
| Appending to the end of files | Prepend (newest on top) |
| Writing entries without agent tag | Every entry must have `[agent-tag]` |
