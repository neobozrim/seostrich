# Memory System — Agent Protocol

You are an agent using a shared blackboard memory system. Your memory directory
contains the files listed below. Read this protocol before every run. Follow it
exactly.

## Your memory directory

```
memory/
  tasks.md            shared task board — coordination with other agents
  facts.md            observed truths about the user/world (incl. preferences)
  learnings.md        rules you concluded from experience
  decisions.md        specific choices made for the future
  runs-summaries.md   one summary per run (accumulating history)
  artefacts-index.md  index of durable deliverables
  artefacts/          the deliverables themselves
```

## Datetime format

ISO 8601 to the minute, UTC, no seconds: `YYYY-MM-DDThh:mm`
Example: `2026-07-01T14:30`

## Your agent name

Every entry you write must be tagged with your agent name. Use the name assigned
to you (e.g. `tech-seo`, `general-seo`, `branding`). Never leave entries
unattributed.

## Universal rules

- **Tag everything** with your agent name.
- **Only edit your own entries.** Exception: you may supersede another agent's
  entry (see §Supersede below).
- **Read before you write.** Always read the relevant file before appending.
- **Read before you act.** Check `tasks.md` for conflicts before starting work.
  Check `facts.md`, `learnings.md`, `decisions.md` for relevant context.

## What is a run?

A run is one self-contained goal the user gave you. Refinements and follow-ups
on the same goal are the same run. A run ends only when the user gives a
**totally different goal**.

## What you do during a run

### 1. Plan
Break the goal into tasks. Post each to `tasks.md` as a `to do` line:
```
#{agent-name} | to do | {task goal} | affects: {files/assets/pages it will touch}
```

### 2. Coordinate
Before picking up a task, read `tasks.md`. If another agent's `in progress` task
touches the same files, wait or pick non-overlapping work.

### 3. Load context
Read relevant parts of `facts.md`, `learnings.md`, `decisions.md` (skip
superseded entries). Check `artefacts-index.md` for relevant deliverables.

### 4. Work
- Set task status to `in progress` when starting, `done` when finishing.
- Create/update artefacts as needed (see §Artefacts).
- Record new facts, learnings, decisions as they arise.

### 5. Record learnings
- **Fact** (observed truth): append to `facts.md`:
  ```
  [{agent-name}][{datetime}] {the fact}
  ```
- **Learning** (concluded rule): append to `learnings.md`:
  ```
  [{agent-name}][{datetime}] {the rule}
  ```
- **Decision** (choice for the future): append to `decisions.md`:
  ```
  [{agent-name}][{datetime}] {the choice, and optionally the expectation}
  ```

### 6. Finalize at run boundary
- Write or revise your run summary in `runs-summaries.md` as `final`:
  ```
  ## {datetime} | {agent-name} | {short goal} | final
  Goal: {goal description}
  Did: {what you did}
  Found: {what you discovered}
  Artefacts: {links to any artefact touched, or "none"}
  ```
- You may write a `draft` summary mid-run if useful. At run end, revise it to `final`.
- Run your compaction pass (see §Supersede & Compaction).
- Mark all your tasks as `done`.

## Artefacts

Artefacts are durable deliverables — things the user would want to refer back to.

- **Reuse before create:** scan `artefacts-index.md` first. If a matching
  artefact exists, update it.
- **Declare before create:** list the artefact in your task's `affects:` scope.
- **Write order:** write the artefact file first, then update the index line.

Each artefact file has this structure:
```markdown
# {Title}
## Rationale
{Why it is the way it is — what was chosen and rejected}
## {Content sections}
...
## Changelog
- {datetime} | {agent-name} | {what changed}
```

Index line format in `artefacts-index.md`:
```
{name} | {agent} | {one-line summary} | {location}
```

## Supersede & Compaction

### Supersede (everyday forgetting)
When an entry in `facts.md`, `learnings.md`, or `decisions.md` is no longer true,
strike through its words and append who/when/why:
```
[branding][2026-06-05T11:00] ~~brand voice is casual and friendly~~ (superseded 2026-06-20T14:30 by branding: user redirected to authoritative)
```
- The original text stays, struck through.
- This is the **one edit** you may make to another agent's entry.
- On read, treat struck-through entries as inactive.

### Compaction (occasional cleanup)
During your run finalization, physically remove **your own** struck-through
entries and your own `done`/abandoned task lines. Never remove another agent's
lines. No knowledge is lost — substance is preserved in `runs-summaries.md`.

## Conflict resolution

If two entries from different agents contradict each other:
1. Both stand until one is superseded.
2. When you notice a contradiction with another agent's entry, note it in your
   run summary so the orchestrator or user can resolve it.
