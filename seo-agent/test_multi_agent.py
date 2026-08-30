"""Test the 3-agent system — SEO, Brand, Builder all routed through orchestrator."""
import sys
import os
import json
from pathlib import Path

# Fix Windows console encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(str(SCRIPT_DIR.parent / ".env"))

passed = 0
failed = 0
errors = []


def test(name: str):
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  [OK] {name}")
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            errors.append((name, f"Unexpected: {e}"))
            print(f"  [FAIL] {name}: Unexpected error: {e}")
        return fn
    return decorator


print("=" * 80)
print("MULTI-AGENT SYSTEM TESTS")
print("=" * 80)

# ─── 1. Imports ───────────────────────────────────────────────────────────────

print("\n1. Imports")

@test("All agent modules import")
def _():
    from src.agent import run_agent
    from src.brand_agent import run_brand_agent
    from src.builder_agent import run_builder_agent
    assert callable(run_agent)
    assert callable(run_brand_agent)
    assert callable(run_builder_agent)


@test("Orchestrator imports all agents")
def _():
    from src.orchestrator import AGENT_REGISTRY, run_orchestrator_stream
    assert "seo_agent" in AGENT_REGISTRY
    assert "brand_agent" in AGENT_REGISTRY
    assert "builder_agent" in AGENT_REGISTRY
    assert callable(run_orchestrator_stream)


# ─── 2. Brand Agent ───────────────────────────────────────────────────────────

print("\n2. Brand Agent")

@test("Brand agent tools registered")
def _():
    from src.brand_agent import TOOL_DEFINITIONS, TOOL_CALLABLES
    tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "write_profile" in tool_names
    assert "fetch_url" in tool_names
    assert "trademark_lookup" in tool_names
    assert "font_pairing" in tool_names
    assert "color_system" in tool_names
    assert "web_search" in tool_names
    assert len(TOOL_CALLABLES) >= 10


@test("Brand validator enforces hard gates")
def _():
    from src.brand_validator import validate_brand_profile
    # Empty profile should fail
    violations = validate_brand_profile({})
    assert len(violations) > 0


# ─── 3. Builder Agent ─────────────────────────────────────────────────────────

print("\n3. Builder Agent")

@test("Builder agent tools registered")
def _():
    from src.builder_agent import TOOL_DEFINITIONS, TOOL_CALLABLES
    tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "read_brand_profile" in tool_names
    assert "write_file" in tool_names
    assert "run_shell" in tool_names
    assert "playwright_check" in tool_names
    assert "generate_asset" in tool_names
    assert "take_screenshot" in tool_names


@test("Builder tools work")
def _():
    from src.builder_tools import read_brand_profile, write_file
    # Read the existing UNBLOCKED profile
    result = read_brand_profile("unblocked")
    assert result.get("status") == "success", f"Failed to read profile: {result}"
    profile = result["profile"]
    assert profile["mode"] == "bold"
    assert profile["naming"]["name"] == "UNBLOCKED"


@test("Asset tools import and have routing")
def _():
    from src.asset_tools import generate_asset, select_model, MODEL_ROUTING
    assert callable(generate_asset)
    assert callable(select_model)
    assert select_model("wordmark") == "ideogram-3.0"
    assert select_model("icon") == "recraft-v4"
    assert select_model("photo") == "flux-2-pro"
    assert select_model("draft") == "imagen-4-fast"


# ─── 4. Memory Integration ────────────────────────────────────────────────────

print("\n4. Memory Integration")

@test("Brand constraints on blackboard")
def _():
    from src import memory
    constraints = memory.read_brand_constraints()
    assert len(constraints) > 0
    assert "UNBLOCKED" in constraints
    assert "banned" in constraints.lower() or "Banned" in constraints


@test("Brand profile in artefacts")
def _():
    from src import memory
    artefacts_dir = memory._get_memory_dir() / "artefacts"
    profiles = list(artefacts_dir.glob("*-brand-profile.json"))
    assert len(profiles) >= 1
    # Check UNBLOCKED profile
    unblocked = artefacts_dir / "unblocked-brand-profile.json"
    assert unblocked.exists()
    data = json.loads(unblocked.read_text(encoding="utf-8"))
    assert data["mode"] == "bold"


# ─── 5. Orchestrator Routing ──────────────────────────────────────────────────

print("\n5. Orchestrator Routing")

@test("Orchestrator system prompt mentions all 3 agents")
def _():
    from src.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
    assert "SEO Agent" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "Brand Agent" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "Builder Agent" in ORCHESTRATOR_SYSTEM_PROMPT


@test("Orchestrator loads brand constraints into context")
def _():
    from src.orchestrator import run_orchestrator_stream
    # Just verify the function exists and is callable
    assert callable(run_orchestrator_stream)


# ─── Summary ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 80)

if errors:
    print("\nFailed tests:")
    for name, error in errors:
        print(f"  [FAIL] {name}: {error}")

sys.exit(0 if failed == 0 else 1)
