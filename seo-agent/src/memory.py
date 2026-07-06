"""Blackboard memory integration for the SEO agent.

Reads and writes to the shared blackboard memory system.
Path is configurable via MEMORY_DIR environment variable.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def _get_memory_dir() -> Path:
    """Get the memory directory from environment or use relative path."""
    env_path = os.getenv("MEMORY_DIR")
    if env_path:
        return Path(env_path) / "agents"
    
    # Fallback: relative to this file (src/memory.py)
    # Goes up: memory.py -> src/ -> seo-agent/ -> qwen/ -> agent-memory/
    project_root = Path(__file__).resolve().parent.parent
    qwen_root = project_root.parent
    agent_memory = qwen_root / "agent-memory"
    
    if not agent_memory.exists():
        # Try creating it if we're in a fresh deployment
        agent_memory.mkdir(parents=True, exist_ok=True)
        (agent_memory / "agents").mkdir(exist_ok=True)
    
    return agent_memory / "agents"


MEMORY_DIR = _get_memory_dir()
AGENT_NAME = "seo-agent"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _append(filename: str, line: str) -> None:
    if not MEMORY_DIR.exists():
        return
    path = MEMORY_DIR / filename
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def record_fact(text: str) -> None:
    _append("facts.md", f"[{AGENT_NAME}][{_now()}] {text}")


def record_learning(text: str) -> None:
    _append("learnings.md", f"[{AGENT_NAME}][{_now()}] {text}")


def record_decision(text: str) -> None:
    _append("decisions.md", f"[{AGENT_NAME}][{_now()}] {text}")


def post_task(task_goal: str, affects: str = "") -> None:
    _append("tasks.md", f"#{AGENT_NAME} | in progress | {task_goal} | affects: {affects}")


def complete_task(task_goal: str, affects: str = "") -> None:
    _append("tasks.md", f"#{AGENT_NAME} | done | {task_goal} | affects: {affects}")


def read_facts() -> str:
    path = MEMORY_DIR / "facts.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_learnings() -> str:
    path = MEMORY_DIR / "learnings.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_decisions() -> str:
    path = MEMORY_DIR / "decisions.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_tasks() -> str:
    path = MEMORY_DIR / "tasks.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def record_artefact(name: str, summary: str, location: str) -> None:
    """Record an artefact in the artefacts index."""
    _append("artefacts-index.md", f"{name} | {AGENT_NAME} | {summary} | {location}")


def draft_run_summary(goal: str, did: str, found: str = "", artifacts: str = "") -> None:
    """Write a draft run summary (can be called mid-run by the agent)."""
    now = _now()
    summary = (
        f"## {now} | {AGENT_NAME} | {goal[:50]} | draft\n"
        f"Goal: {goal}\n"
        f"Did: {did}\n"
        f"Found: {found or 'nothing notable'}\n"
        f"Artefacts: {artifacts or 'none'}"
    )
    _append("runs-summaries.md", summary)


def finalize_run_summary(goal: str, did: str, found: str = "", artifacts: str = "") -> None:
    """Finalize a run summary (called by orchestrator at run end)."""
    now = _now()
    summary = (
        f"## {now} | {AGENT_NAME} | {goal[:50]} | final\n"
        f"Goal: {goal}\n"
        f"Did: {did}\n"
        f"Found: {found or 'nothing notable'}\n"
        f"Artefacts: {artifacts or 'none'}"
    )
    _append("runs-summaries.md", summary)
