"""CLI tool for reviewing and applying improvement proposals."""
import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from . import memory


def list_pending_proposals() -> List[Path]:
    """List all pending improvement proposals."""
    improvements_dir = memory._get_memory_dir() / "improvements"
    if not improvements_dir.exists():
        return []
    
    proposals = []
    for filepath in sorted(improvements_dir.glob("proposal-*.md")):
        content = filepath.read_text(encoding="utf-8")
        if "**Status:** pending" in content:
            proposals.append(filepath)
    
    return proposals


def display_proposal(filepath: Path) -> str:
    """Display a proposal and return user action."""
    content = filepath.read_text(encoding="utf-8")
    
    print("\n" + "="*80)
    print(f"Proposal: {filepath.name}")
    print("="*80)
    print(content)
    print("="*80)
    
    while True:
        action = input("\nAction [a]pply / [r]eject / [s]kip / [q]uit: ").strip().lower()
        if action in ['a', 'apply', 'r', 'reject', 's', 'skip', 'q', 'quit']:
            return action
        print("Invalid action. Please enter a/r/s/q.")


def update_proposal_status(filepath: Path, status: str) -> None:
    """Update the status of a proposal."""
    content = filepath.read_text(encoding="utf-8")
    updated = content.replace("**Status:** pending", f"**Status:** {status}")
    filepath.write_text(updated, encoding="utf-8")


def apply_improvement(filepath: Path) -> bool:
    """Apply an improvement proposal."""
    content = filepath.read_text(encoding="utf-8")
    
    # Check if it's a missing memories proposal
    if "**Type:** missing_memories" in content:
        print("[Apply] Processing missing memories proposal...")
        # These are already applied by the self-learning loop
        # Just mark as applied
        update_proposal_status(filepath, "applied")
        print("✓ Marked as applied (memories were added during analysis)")
        return True
    
    # Parse improvement proposal
    category = _extract_field(content, "Category")
    proposed_change = _extract_field(content, "Proposed Change")
    implementation = _extract_field(content, "Implementation")
    
    if not proposed_change:
        print("⚠ Could not parse proposal")
        return False
    
    # Apply based on category
    if category == "Tool Design":
        print(f"[Apply] Tool design improvement:")
        print(f"  Change: {proposed_change}")
        print(f"  Implementation: {implementation}")
        print("\n  ⚠ Tool design changes require manual implementation")
        print("  Review the proposal and update the code accordingly")
        
    elif category == "Prompt Engineering":
        print(f"[Apply] Prompt engineering improvement:")
        print(f"  Change: {proposed_change}")
        print(f"  Implementation: {implementation}")
        print("\n  ⚠ Prompt changes require manual implementation")
        print("  Update system prompts or tool descriptions in the code")
        
    elif category == "Memory Usage":
        print(f"[Apply] Memory usage improvement:")
        print(f"  Change: {proposed_change}")
        # Memory usage improvements are informational
        # They guide how the agent should use memory in future runs
        
    elif category == "Workflow Efficiency":
        print(f"[Apply] Workflow efficiency improvement:")
        print(f"  Change: {proposed_change}")
        print(f"  Implementation: {implementation}")
        print("\n  ⚠ Workflow changes require manual implementation")
        print("  Review and adjust the agent's workflow logic")
    
    update_proposal_status(filepath, "applied")
    print("✓ Marked as applied")
    return True


def reject_proposal(filepath: Path) -> None:
    """Reject a proposal."""
    update_proposal_status(filepath, "rejected")
    print("✓ Marked as rejected")


def _extract_field(content: str, field_name: str) -> str:
    """Extract a field value from markdown content."""
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith(f"**{field_name}:**"):
            # Single line field
            value = line.split(f"**{field_name}:**")[1].strip()
            return value
        elif line.strip() == f"## {field_name}":
            # Multi-line section
            section_lines = []
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("## "):
                    break
                if lines[j].strip():
                    section_lines.append(lines[j].strip())
            return '\n'.join(section_lines)
    return ""


def review_proposals():
    """Main review loop."""
    proposals = list_pending_proposals()
    
    if not proposals:
        print("No pending proposals found.")
        return
    
    print(f"\nFound {len(proposals)} pending proposal(s)")
    
    for filepath in proposals:
        action = display_proposal(filepath)
        
        if action in ['a', 'apply']:
            apply_improvement(filepath)
        elif action in ['r', 'reject']:
            reject_proposal(filepath)
        elif action in ['s', 'skip']:
            print("Skipped")
        elif action in ['q', 'quit']:
            print("\nExiting review")
            break
    
    print("\nReview complete")


if __name__ == "__main__":
    review_proposals()
