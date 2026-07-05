from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "agent-memory" / "agents"

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
