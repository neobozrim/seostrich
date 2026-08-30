"""Memory tools for the SEO agent."""
import json
from typing import Dict, Any


def read_memory(memory_type: str = "all") -> Dict[str, Any]:
    """
    Read memory from the blackboard system.

    Args:
        memory_type: "facts", "learnings", "decisions", "tasks", or "all"

    Returns:
        Dict with memory content
    """
    from .. import memory
    
    result = {}
    
    if memory_type in ("facts", "all"):
        result["facts"] = memory.read_facts()
    if memory_type in ("learnings", "all"):
        result["learnings"] = memory.read_learnings()
    if memory_type in ("decisions", "all"):
        result["decisions"] = memory.read_decisions()
    if memory_type in ("tasks", "all"):
        result["tasks"] = memory.read_tasks()
    
    return result


def record_fact(fact: str) -> Dict[str, Any]:
    """
    Record an observed truth to facts.md.
    
    Examples:
        - "User's blog has 5 posts"
        - "productpirates.club is not indexed by Google"
        - "DataForSEO keyword limit is 100 per request"
    
    Args:
        fact: The observed truth to record
    
    Returns:
        Success status
    """
    from .. import memory
    memory.record_fact(fact)
    return {"status": "success", "recorded": "fact", "content": fact}


def record_learning(learning: str) -> Dict[str, Any]:
    """
    Record a concluded rule or pattern to learnings.md.
    
    Examples:
        - "Staggering blog post publication dates looks more natural to Google"
        - "Qwen Cloud token plan keys use different base URL than pay-as-you-go"
        - "User prefers minimal tools — use web_search instead of dedicated scrapers"
    
    Args:
        learning: The rule or pattern learned
    
    Returns:
        Success status
    """
    from .. import memory
    memory.record_learning(learning)
    return {"status": "success", "recorded": "learning", "content": learning}


def record_decision(decision: str) -> Dict[str, Any]:
    """
    Record a choice made and why to decisions.md.
    
    Examples:
        - "Using productpirates.club for testing (blog.yavorpopov.com is temporary)"
        - "Astro chosen over WordPress for full control over meta tags"
        - "Removed analyze_competitor tool — web_search handles this use case"
    
    Args:
        decision: The choice made (and optionally why)
    
    Returns:
        Success status
    """
    from .. import memory
    memory.record_decision(decision)
    return {"status": "success", "recorded": "decision", "content": decision}


def tool_post_task(task_goal: str, affects: str = "") -> Dict[str, Any]:
    """
    Post a new task to the tasks board.

    Args:
        task_goal: What needs to be done (short description)
        affects: Which systems/areas this task touches

    Returns:
        Success status
    """
    from .. import memory
    memory.post_task(task_goal, affects)
    return {"status": "success", "recorded": "task", "content": task_goal}


def tool_complete_task(task_goal: str, affects: str = "") -> Dict[str, Any]:
    """
    Mark a task as completed on the tasks board.

    Args:
        task_goal: The task that was completed
        affects: Which systems/areas this task touched

    Returns:
        Success status
    """
    from .. import memory
    memory.complete_task(task_goal, affects)
    return {"status": "success", "completed": "task", "content": task_goal}


def tool_record_artefact(name: str, summary: str, location: str) -> Dict[str, Any]:
    """
    Record a durable deliverable/artefact in the artefacts index.

    Args:
        name: Artefact name (e.g., "article-seo-best-practices.md")
        summary: Short description of the artefact
        location: File path or URL where it lives

    Returns:
        Success status
    """
    from .. import memory
    memory.record_artefact(name, summary, location)
    return {"status": "success", "recorded": "artefact", "name": name}


def tool_draft_run_summary(goal: str, did: str, found: str = "", artifacts: str = "") -> Dict[str, Any]:
    """
    Draft a run summary (can be called mid-run when wrapping up).

    Args:
        goal: What this run aimed to accomplish
        did: What was actually done
        found: Notable findings or discoveries
        artifacts: Artefacts produced during this run

    Returns:
        Success status
    """
    from .. import memory
    memory.draft_run_summary(goal, did, found, artifacts)
    return {"status": "success", "recorded": "run_summary", "goal": goal}
