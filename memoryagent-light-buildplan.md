# MemoryAgent — Build Spec (Track 1)

A memory layer for a set of AI agents, inspired by the **blackboard
architecture**: a small set of shared files that all agents read and write, so
knowledge accumulates across sessions, preferences and decisions persist, and each
agent gets more accurate over time. The memory is plain markdown — human-readable,
directly inspectable, and requires no database. This spec is domain-agnostic; the
example agents (tech-SEO, general-SEO, geo, branding) are one deployment.

---

## 1. The files

```
memory/
  tasks.md            purpose §4 · a shared board of every agent's planned/in-progress/
                      done tasks, for cross-agent coordination
  facts.md            purpose §5 · observed truths about the user/world/site (incl. preferences)
  learnings.md        purpose §6 · rules derived from experience (concluded, not observed)
  decisions.md        purpose §7 · specific choices made for the future; outcome added later if known
  runs-summaries.md   purpose §8 · one summary per run (the accumulating history)
  artefacts-index.md  purpose §9 · index of durable deliverables (name, agent, summary, location)
  artefacts/          purpose §9 · the deliverables themselves, one living file per artefact
```

**Initialization.** On first use none of this exists. The orchestrator creates
`memory/` and `artefacts/`, and creates each `.md` file empty (or with just its
`# title` line). An empty file is a valid state, not an error.

**Two universal rules across all shared files:**
- **Tagging.** Every entry names the agent that wrote it, so shared never means
  unattributable — filter by agent name to see one agent's contributions.
- **Ownership.** An agent adds, edits, and removes only **its own** entries. The
  one exception is marking another agent's entry superseded (§10), which is a
  narrow, annotated flag — never a rewrite of their content.

Datetimes everywhere use ISO 8601 to the minute, UTC, no seconds:
`YYYY-MM-DDThh:mm` (e.g. `2026-05-24T16:04`).

---

## 2. Runs (the unit that drives the whole system)

A **run is one self-contained goal the user gave the agent.** It may span many
user turns — refinements and follow-ups on the same goal are all the same run. A
run ends only when the user gives a **totally different goal**.

Why this matters: the end of a run is when the agent finalizes its summary and its
**context is cleared** (§3). Nothing is cleared before that. So the run boundary is
the single most important signal in the system.

- **Sub-steps are not runs.** "Audit my homepage SEO" is one run — all the
  crawling, checking, and reporting inside it included.
- **Refinement is the same run.** "audit it" → "focus on the blog" → "skip the
  images" is one run.
- **Autonomous expansion is the same run.** If the agent checks something extra
  because it is relevant, still the same run — no new user goal drove it.
- **A new run** begins only when the user changes direction to a different goal.

**What an agent does across a run:**
1. **Plan.** It breaks the goal into concrete tasks and posts them to `tasks.md`
   (§4). Planning is the origin of tasks.
2. **Coordinate.** Before acting on a task it reads the other tasks on the board to
   spot conflicts (§4) — another agent or session touching the same files, or a
   task its own work depends on — and may wait for that work to finish first.
3. **Load context.** It reads only the relevant parts of `facts`, `learnings`,
   `decisions` (ignoring superseded entries), and any relevant artefact via
   `artefacts-index.md`. The knowledge files are already the compressed view, so it
   loads only what the task needs.
4. **Work**, updating each task's status as it goes (§4), and creating/updating any
   durable deliverable as an artefact (§9).
5. **Record as it learns.** It writes new facts/learnings/decisions when it
   discovers them (§5–§7), and may write a **draft** run summary when useful (§8).
6. **Finalize** at the run boundary: promote or revise its summary to `final` (§8),
   record any remaining learnings, and mark stale entries superseded (§10).

---

## 3. Clearing context (orchestration, not an agent action)

The model (Qwen) is stateless per call; "context" is simply the message history
the orchestrator passes in, which grows on its own as the conversation continues.
The agent never manages this — it only writes to the memory **files**. Clearing
context is purely an orchestrator behavior at the run boundary:

- When a new user message arrives, the orchestrator judges: **same goal, or a
  totally different goal?**
- **Same goal** → the run continues; the growing context carries forward; the agent
  may create or update its draft summary (§8).
- **Totally different goal** → the agent finalizes (§2 step 6), then the
  orchestrator **starts the next run with a fresh context** — the system prompt
  plus the freshly re-read memory files, and none of the previous run's turns.

Continuity across runs therefore comes entirely from the persisted files, not from
retained conversation. For v1 the same-vs-different-goal judgment is a simple LLM
classification, biased toward "same goal" so context is not cleared while the user
is still shaping one goal.

---

## 4. tasks.md

**Purpose.** A shared board of every agent's tasks, so agents coordinate: each can
see what others are doing, avoid working the same files at once, and read a
realistic state of progress toward a plan. Ordered newest on top.

**Line format:**
```
#{agent-name} | {status} | {task goal} | affects: {files/assets/pages it will touch}
```
`status` is one of **`to do`**, **`in progress`**, **`done`**.

**Rules for writing:**
- **On planning**, an agent posts its tasks as `to do` lines (a run usually yields
  several). Each names the parts of the system it will touch (`affects:`) — this is
  what lets other agents judge overlap.
- **Before picking up a task**, the agent reads the board's other `to do` /
  `in progress` lines. If another agent's or session's in-progress task touches the
  same files, or if its own task depends on work not yet done, it **waits** until
  that task is finished, or picks non-overlapping work.
- **On starting a task**, it sets that line to `in progress`.
- **On finishing a task**, it sets that line to `done` — done incrementally, per
  task, so the board reflects real progress.
- `done` lines and abandoned lines stay on the board until removed at **compaction**
  (§10) by their own author. An agent never edits another agent's line.

**Example:**
```
#tech-seo  | in progress | audit internal links on category pages | affects: pages/category/*
#branding  | done        | refresh brand-voice | affects: facts.md (brand-voice), artefacts/brand-guide.md
#tech-seo  | done        | review keyword targets for /best-running-shoes | affects: decisions.md, artefacts/seo-strategy.md
```

**Concurrency.** Agents may run in parallel. Logical overlap is avoided by the
board (read `affects:` before acting). Write corruption is avoided by making every
shared-file write atomic — a plain append where possible, and for the non-append
writes (setting a status, superseding an entry, compaction) a read-modify-write
under a brief per-file lock, so one write cannot drop another's. Full transactional
locking is out of scope for v1.

---

## 5. facts.md

**Purpose.** Observed truths about the user, the world, or the site that the agent
did not decide and cannot change — the site domain, the user's region, and **user
preferences** (a preference is an observed truth about what the user wants). Test:
*was this observed?* → fact.

**Line format:**
```
[{agent-name}][{datetime}] {the fact, in plain prose}
```

**Rules for writing:** append a line when a new observed truth is discovered.
Never overwrite a fact; if it becomes untrue, mark it superseded (§10). Entries are
identified by their exact line text (§10).

**Example:**
```
[tech-seo][2026-06-10T09:00] user dislikes AI-generated copy; hand-write it.
[branding][2026-06-20T14:30] brand voice is authoritative and expert, not casual; no emoji.
```

---

## 6. learnings.md

**Purpose.** Generalized rules the agent concluded from experience, applicable to
future situations. Test: *was this concluded from experience, and could it guide a
future, different task?* → learning. (Contrast: a fact is observed, not concluded.)

**Line format:**
```
[{agent-name}][{datetime}] {the rule, in plain prose}
```

**Rules for writing:** append a line when reflection yields a durable rule. It is
read before acting so past lessons inform new work. Supersede it (§10) if it stops
holding.

**Example:**
```
[tech-seo][2026-07-29T16:00] long-tail low-competition targets beat head terms for this site.
[general-seo][2026-06-12T11:00] thin pages get deindexed fast — keep 800+ words.
```

---

## 7. decisions.md

**Purpose.** Specific choices made for the future that could affect the system or
the work. A decision stands on its own — **an outcome is optional**, added later
if and when the result is known. Test: *is this a deliberate choice we made?* →
decision.

**Line format:**
```
[{agent-name}][{datetime}] {the choice, and optionally the expectation/bet}
[{agent-name}][{datetime}] outcome of {the earlier decision}: {what happened}   ← optional, later
```

**Rules for writing:** append a decision when one is made. If its result later
becomes known, append an outcome line referencing it. Reflecting on an outcome may
produce a learning (§6). Supersede a decision (§10) if it is overturned.

**Example:**
```
[tech-seo][2026-06-01T10:00] switch primary target running-shoes → trail-shoes; expect top-5 in ~8 weeks.
[tech-seo][2026-07-29T16:00] outcome of the 2026-06-01 target switch: reached position 3 in 7 weeks.
```

---

## 8. runs-summaries.md

**Purpose.** One summary per run — the accumulating history, and the source for
answering "what did we do about X and how did it turn out" (search this file plus
`decisions.md` and read matches in date order).

**Block format:**
```
## {datetime} | {agent-name} | {short goal} | {draft|final}
Goal: {goal description}
Did: {what the agent did}
Found: {what it discovered}
Artefacts: {links to any artefact touched, or "none"}
```
One blank line separates blocks. Each block carries a **status: `draft` or
`final`**.

**Rules for writing:**
- The agent may write a **draft** summary when useful — for a complex goal
  mid-way, or when it judges the goal satisfied but the user has not yet confirmed
  by moving on.
- At the run boundary the agent **must check whether its draft summary exists**; if
  so, it revises it as needed and marks it **`final`**; if not, it writes the
  summary directly as `final`.
- A `draft` block may be edited by its author; a `final` block is frozen. No block
  is ever deleted or trimmed.

**Example:**
```
## 2026-06-24T16:30 | tech-seo | keyword targeting review | final
Goal: review and improve keyword targets for /best-running-shoes.
Did: analyzed competitor-x; recommended switching primary target to trail-shoes.
Found: trail-shoes lower competition, rising volume; user dislikes AI meta copy.
Artefacts: updated artefacts/seo-strategy.md.
```

---

## 9. Artefacts

**Purpose.** Memory records what happened; artefacts are what was **produced** — a
strategy, a content calendar, an analysis — so an agent can improve real prior work
rather than reconstruct it from a summary. Something is an artefact if the user
would plausibly want to refer back to it or build on it; a one-off answer is not.

**Structure.** One **living file per artefact**, updated in place (never
`-v2`), so there is exactly one place each deliverable lives. Each artefact file
carries a short **Rationale** (why it is the way it is — what was chosen and
rejected), the content, and a **Changelog** at the bottom:
```markdown
# SEO Strategy
## Rationale
Targets long-tail low-competition keywords (user prefers them, site converts better);
a paid-ads angle was considered and rejected on budget.
## Strategy
... the current strategy ...
## Changelog
- 2026-06-25T11:00 | tech-seo | revised competitor angle after competitor-x backlink shift
- 2026-06-24T09:30 | tech-seo | added long-tail keyword section
```
The reasoning that led to a deliverable lives in its Rationale — raw discussion is
not kept; its substance flows into the summary, decisions, learnings, and the
rationale.

**artefacts-index.md** is the small index agents read first to find deliverables,
one line each:
```
{name} | {agent that last created/acted on it} | {one-line summary} | {location}
```
```
seo-strategy | tech-seo | long-tail-focused SEO strategy for the site | artefacts/seo-strategy.md
```

**Rules for writing:**
- **Reuse before create:** scan the index first; if a matching artefact exists,
  update it rather than making a new one. Anything not in the index is not a
  maintained artefact.
- **Declare it:** because agents run in parallel, list the artefact in the task's
  `affects:` scope (§4) before creating/editing it, so another agent does not
  create the same one simultaneously.
- **Write order:** write the artefact file, then add/update its index line, so the
  index never points at a missing file.

---

## 10. Forgetting: supersede + compaction

Outdated knowledge must stop influencing decisions without being silently lost.
Two mechanisms, applying to **`facts.md`, `learnings.md`, and `decisions.md` only**
(not `tasks.md`, not `runs-summaries.md`):

**Supersede — the everyday, safe act.** When an entry is no longer true, strike
through its words (keeping them intact) and append who/when/why:
```
[branding][2026-06-05T11:00] ~~brand voice is casual and friendly~~ (superseded 2026-06-20T14:30 by branding: user redirected to authoritative)
```
The original words stay, struck through — not deleted or rewritten. **This is the
one edit an agent may make to another agent's entry.** On read, an agent treats a
superseded entry as inactive (the current view is the un-struck entries), so
retired knowledge no longer affects decisions — that is the "forgetting." An entry
is identified for supersession by its exact full line text; if two would collide
(same agent, same minute, same words), the writer appends `#2` to the datetime to
keep each line unique.

**Compaction — occasional, own-entries-only.** Struck-through entries (and `done`/
abandoned `tasks.md` lines) accumulate. During its finalization each agent
physically removes **its own** retired entries. Because an agent only rewrites its
own lines, this never clobbers another agent's concurrent write. It is not
scheduled and not size-based — it happens as part of finalizing a run. It only
removes already-superseded content, whose substance is preserved in
`runs-summaries.md`, so no live knowledge is lost. (An entry superseded by a
different agent lingers, harmlessly filtered on read, until its own author next
compacts.)
