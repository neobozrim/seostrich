# Agent Memory

A blackboard-style shared memory system for AI agents.

## Structure

```
agent-memory/
├── PROTOCOL.md          — shared protocol all agents follow
├── qwen/                — Qwen Code's own memory instance
│   ├── tasks.md         — shared task board
│   ├── facts.md         — observed truths
│   ├── learnings.md     — rules concluded from experience
│   ├── decisions.md     — choices made for the future
│   ├── runs-summaries.md— one summary per run
│   ├── artefacts-index.md— index of durable deliverables
│   └── artefacts/       — the deliverables themselves
└── agents/              — separate instance for future agents
    ├── (same structure)
```

## How it works

- Agents read the protocol before every run
- Each entry is tagged with the agent name and timestamp
- Old entries are struck through, never deleted (substance preserved in run summaries)
- Agents coordinate via the shared `tasks.md` board
- Artefacts are durable deliverables with rationale and changelog

See `memoryagent-light-buildplan.md` for the original build specification.
