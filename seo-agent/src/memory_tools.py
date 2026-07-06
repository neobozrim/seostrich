"""Memory tools for the SEO agent."""
from __future__ import annotations

from ..memory import (
    read_facts, read_learnings, read_decisions, read_tasks,
    record_fact, record_learning, record_decision,
    post_task, complete_task, record_artefact,
    draft_run_summary, finalize_run_summary
)


def read_memory(memory_type: str = "all") -> dict:
    """Read memory from the blackboard.
    
    Args:
        memory_type: "facts", "learnings", "decisions", "tasks", or "all"
    """
    result = {}
    if memory_type in ("facts", "all"):
        result["facts"] = read_facts()
    if memory_type in ("learnings", "all"):
        result["learnings"] = read_learnings()
    if memory_type in ("decisions", "all"):
        result["decisions"] = read_decisions()
    if memory_type in ("tasks", "all"):
        result["tasks"] = read_tasks()
    return result


def tool_post_task(task_goal: str, affects: str = "") -> dict:
    """Post a task to the blackboard."""
    post_task(task_goal, affects)
    return {"status": "posted", "task": task_goal}


def tool_complete_task(task_goal: str, affects: str = "") -> dict:
    """Mark a task as completed on the blackboard."""
    complete_task(task_goal, affects)
    return {"status": "completed", "task": task_goal}


def tool_record_artefact(name: str, summary: str, location: str) -> dict:
    """Record an artefact in the blackboard."""
    record_artefact(name, summary, location)
    return {"status": "recorded", "artefact": name}


def tool_draft_run_summary(goal: str, did: str, found: str = "", artifacts: str = "") -> dict:
    """Draft a run summary (agent can call this mid-run)."""
    draft_run_summary(goal, did, found, artifacts)
    return {"status": "drafted"}
