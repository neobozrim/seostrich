"""Test the self-learning loop against real Braintrust sessions.

This script does NOT write any data to Braintrust.
It reads existing real sessions and runs self-learning on them.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Resolve paths relative to this script, not CWD
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Add project root to path
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from the qwen root (parent of seo-agent)
from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
load_dotenv(str(env_path))
print(f"Loaded .env from: {env_path}")

from src.tools.braintrust import read_braintrust_trace, list_recent_sessions
from src.tools.self_learning import run_self_learning
from src import memory

print("=" * 80)
print("SELF-LEARNING LOOP TEST (read-only from Braintrust)")
print("=" * 80)

# Step 1: List recent real sessions from Braintrust
print("\n1. Fetching recent sessions from Braintrust...")
recent = list_recent_sessions(limit=10)
if not recent:
    print("   ✗ No sessions found in Braintrust. Run the SEO agent first to create real sessions.")
    sys.exit(1)

print(f"   Found {len(recent)} session(s):")
for sid in recent:
    print(f"   - {sid}")

# Step 2: Pick a real session (most recent)
session_id = recent[0]
print(f"\n2. Testing with session: {session_id}")

# Step 3: Read the trace
print("\n3. Reading trace from Braintrust...")
trace = read_braintrust_trace(session_id)
if not trace:
    print(f"   ✗ Could not read trace for {session_id}")
    sys.exit(1)

print(f"   ✓ Trace found!")
print(f"     Messages: {len(trace.get('messages', []))}")
print(f"     Tool results: {len(trace.get('tool_results', []))}")
print(f"     Tags: {trace.get('tags', [])}")

# Step 4: Read current memory state
print("\n4. Reading current memory state...")
memories_before = memory.read_all()
print(f"   Facts: {len(memories_before['facts'])}")
print(f"   Learnings: {len(memories_before['learnings'])}")
print(f"   Decisions: {len(memories_before['decisions'])}")
print(f"   Tasks: {len(memories_before['tasks'])}")

# Step 5: Run self-learning
print(f"\n5. Running self-learning on {session_id}...")
result = run_self_learning(session_id)
print(f"\n6. Result:")
print(f"   Status: {result.get('status')}")
print(f"   Improvements proposed: {result.get('improvements_proposed', 0)}")
print(f"   Missing memories added: {result.get('missing_memories_added', 0)}")
print(f"   Proposals stored: {result.get('proposals_stored', 0)}")

# Step 6: Check proposal files
print("\n7. Checking proposal files...")
improvements_dir = PROJECT_ROOT / "agent-memory" / "improvements"
if improvements_dir.exists():
    proposals = list(improvements_dir.glob("proposal-*.md"))
    print(f"   Found {len(proposals)} proposal file(s):")
    for p in sorted(proposals)[-3:]:
        print(f"   - {p.name}")
else:
    print("   No proposals directory found")

# Step 7: Check if memories were added
print("\n8. Checking if memories were added...")
memories_after = memory.read_all()
facts_diff = len(memories_after['facts']) - len(memories_before['facts'])
learnings_diff = len(memories_after['learnings']) - len(memories_before['learnings'])
decisions_diff = len(memories_after['decisions']) - len(memories_before['decisions'])

if facts_diff > 0:
    print(f"   ✓ Added {facts_diff} new fact(s)")
if learnings_diff > 0:
    print(f"   ✓ Added {learnings_diff} new learning(s)")
if decisions_diff > 0:
    print(f"   ✓ Added {decisions_diff} new decision(s)")
if facts_diff == 0 and learnings_diff == 0 and decisions_diff == 0:
    print("   No new memories added")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)

if result.get("status") == "error":
    print(f"\n⚠ Error: {result.get('message')}")
    sys.exit(1)
else:
    print("\n✓ Self-learning loop executed successfully against real data")
    print(f"\nNext steps:")
    print(f"  - Review proposals: python -m src.improvements")
    print(f"  - Check Braintrust: https://www.braintrust.dev")
    sys.exit(0)
