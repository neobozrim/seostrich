"""Blackboard memory must be OFF by default, in prompts and in tools.

The blackboard is shared across every project in this repo. With it on, a
Product Pirates conversation was handed Bulgarian coffee-roastery facts and
Neobozrim theatre brand decisions — cross-project contamination that reads as
the model inventing an unrelated industry.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import memory
from src.agent import select_tools_for_intent, _core_tools
from src.config import memory_enabled, reflection_enabled, settings

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


MEM_TOOLS = {"read_memory", "record_fact", "record_learning", "record_decision"}

print("1. off by default")
chk("memory disabled", memory_enabled() is False)
chk("reflection follows the same switch", reflection_enabled() is False)

print("2. no memory tools reach the model")
chk("core set excludes them", not (set(_core_tools()) & MEM_TOOLS))
for msg in ("Create SEO strategy", "keyword research", "audit my site", "hello"):
    names = {d["function"]["name"] for d in select_tools_for_intent(msg)}
    chk(f"{msg[:24]!r:28} no memory tools", not (names & MEM_TOOLS), str(names & MEM_TOOLS))

print("3. the blackboard still holds other projects' data")
blob = memory.read_facts() + memory.read_learnings() + memory.read_decisions()
foreign = [w for w in ("coffee", "roaster", "theatre", "Neobozrim") if w.lower() in blob.lower()]
chk("cross-project entries present (so gating matters)", bool(foreign), str(foreign))
print(f"     blackboard holds {len(blob)} chars including: {foreign}")

print("4. switching it on restores everything")
settings.agent_memory = "on"
try:
    chk("memory_enabled true", memory_enabled() is True)
    chk("core set includes memory tools", bool(set(_core_tools()) & MEM_TOOLS))
    names = {d["function"]["name"] for d in select_tools_for_intent("Create SEO strategy")}
    chk("model gets them back", bool(names & MEM_TOOLS))
finally:
    settings.agent_memory = "off"
chk("restored to off", memory_enabled() is False)

print("5. the alias still works for anyone using the old name")
settings.agent_memory = "on"
chk("AGENT_REFLECTION alias maps to the same switch", reflection_enabled() is True)
settings.agent_memory = "off"

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
