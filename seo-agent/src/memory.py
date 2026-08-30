"""Blackboard memory — single shared store for all agents.

All agents (seo-agent, qwen coding agent) read/write to the same memory files.
Each entry is tagged with the agent name for attribution: [seo-agent], [qwen], etc.

Path is configurable via MEMORY_DIR environment variable, defaults to
agent-memory/ relative to the qwen project root.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def _get_memory_dir() -> Path:
    """Get the memory directory from environment or use relative path."""
    env_path = os.getenv("MEMORY_DIR")
    if env_path:
        p = Path(env_path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Fallback: relative to this file (src/memory.py)
    # Goes up: memory.py -> src/ -> seo-agent/ -> qwen/ -> agent-memory/
    project_root = Path(__file__).resolve().parent.parent
    qwen_root = project_root.parent
    agent_memory = qwen_root / "agent-memory"

    if not agent_memory.exists():
        agent_memory.mkdir(parents=True, exist_ok=True)

    return agent_memory


MEMORY_DIR = _get_memory_dir()
AGENT_NAME = "seo-agent"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _prepend(filename: str, line: str) -> None:
    """Prepend a line to a memory file (newest entries on top).

    Preserves any header line (starting with #) at the top of the file.
    """
    memory_dir = _get_memory_dir()
    if not memory_dir.exists():
        return
    path = memory_dir / filename
    existing = ""
    header = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        lines = existing.split("\n")
        if lines and lines[0].startswith("#"):
            header = lines[0] + "\n"
            existing = "\n".join(lines[1:])

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + line + "\n" + existing)


def record_fact(text: str, agent: str = AGENT_NAME) -> None:
    _prepend("facts.md", f"[{agent}][{_now()}] {text}")


def record_learning(text: str, agent: str = AGENT_NAME) -> None:
    _prepend("learnings.md", f"[{agent}][{_now()}] {text}")


def record_decision(text: str, agent: str = AGENT_NAME) -> None:
    _prepend("decisions.md", f"[{agent}][{_now()}] {text}")


def post_task(task_goal: str, affects: str = "", agent: str = AGENT_NAME) -> None:
    _prepend("tasks.md", f"[{agent}][{_now()}] {task_goal} | status: in progress | affects: {affects}")


def complete_task(task_goal: str, affects: str = "", agent: str = AGENT_NAME) -> None:
    """Complete a task by updating the existing in-progress line or prepending a new one.
    
    Finds the most recent task with matching goal and "status: in progress",
    updates it to "status: done" with current timestamp. If no matching
    in-progress task exists, prepends a new completed task line.
    """
    memory_dir = _get_memory_dir()
    if not memory_dir.exists():
        return
    
    path = memory_dir / "tasks.md"
    if not path.exists():
        # No tasks file, prepend new completed task
        _prepend("tasks.md", f"[{agent}][{_now()}] {task_goal} | status: done | affects: {affects}")
        return
    
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # Find the most recent in-progress task with matching goal
    # Use fuzzy matching - task_goal might be truncated or slightly different
    task_goal_lower = task_goal.lower()
    updated = False
    
    for i, line in enumerate(lines):
        if "status: in progress" in line and agent in line:
            # Check if this line contains the task goal (fuzzy match)
            line_lower = line.lower()
            # Match if task_goal is contained in the line, or vice versa (for truncated goals)
            if task_goal_lower in line_lower or any(
                word in line_lower for word in task_goal_lower.split()[:5]
            ):
                # Update this line to done
                lines[i] = f"[{agent}][{_now()}] {task_goal} | status: done | affects: {affects}"
                updated = True
                break
    
    if updated:
        # Write back the updated content
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    else:
        # No matching in-progress task found, prepend new completed task
        _prepend("tasks.md", f"[{agent}][{_now()}] {task_goal} | status: done | affects: {affects}")


def read_facts() -> str:
    path = _get_memory_dir() / "facts.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_learnings() -> str:
    path = _get_memory_dir() / "learnings.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_decisions() -> str:
    path = _get_memory_dir() / "decisions.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_tasks() -> str:
    path = _get_memory_dir() / "tasks.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_brand_constraints() -> str:
    """Read brand constraints from the blackboard (written by Brand Agent)."""
    path = _get_memory_dir() / "brand-constraints.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_all() -> dict:
    """Read all memory files and return as a dict.

    Returns:
        Dict with keys: facts, learnings, decisions, tasks (each is a list of strings)
    """
    memory_dir = _get_memory_dir()

    def _read_file(filename: str) -> list:
        path = memory_dir / filename
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8")
        lines = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                lines.append(line)
        return lines

    return {
        "facts": _read_file("facts.md"),
        "learnings": _read_file("learnings.md"),
        "decisions": _read_file("decisions.md"),
        "tasks": _read_file("tasks.md")
    }


def record_artefact(name: str, summary: str, location: str) -> None:
    """Record an artefact in the artefacts index."""
    _prepend("artefacts-index.md", f"{name} | {AGENT_NAME} | {summary} | {location}")


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
    _prepend("runs-summaries.md", summary)


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
    _prepend("runs-summaries.md", summary)


def load_skills(agent_name: str = "seo-agent") -> str:
    """Load skills applicable to the given agent from skills/ directory.

    Reads SKILL.md files from the skills/ directory, parses frontmatter,
    and returns concatenated skill content for agents where applies_to matches.

    Args:
        agent_name: The name of the agent (e.g., "seo-agent", "orchestrator")

    Returns:
        String containing concatenated skill content, or empty string if no skills found
    """
    import re

    # Go up from memory.py -> src/ -> seo-agent/ -> qwen/ -> skills/
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    if not skills_dir.exists():
        return ""

    skill_contents = []

    for skill_folder in skills_dir.iterdir():
        if not skill_folder.is_dir():
            continue

        skill_file = skill_folder / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")

            # Parse frontmatter
            frontmatter_match = re.match(
                r"^---\s*\n(.*?)\n---\s*\n(.*)$",
                content,
                re.DOTALL
            )

            if not frontmatter_match:
                continue

            frontmatter_text = frontmatter_match.group(1)
            skill_body = frontmatter_match.group(2)

            # Parse frontmatter key-value pairs
            applies_to_match = re.search(r"applies_to:\s*\[(.*?)\]", frontmatter_text)
            if applies_to_match:
                applies_to = [
                    item.strip() for item in applies_to_match.group(1).split(",")
                ]
            else:
                applies_to = []

            # Check if this skill applies to the given agent
            if agent_name in applies_to or "*" in applies_to:
                skill_name_match = re.search(r"name:\s*(\S+)", frontmatter_text)
                skill_name = skill_name_match.group(1) if skill_name_match else skill_folder.name
                skill_contents.append(f"## Skill: {skill_name}\n\n{skill_body}")

        except Exception as e:
            print(f"⚠ Failed to load skill {skill_folder}: {e}")
            continue

    return "\n\n---\n\n".join(skill_contents)
