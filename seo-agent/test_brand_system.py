"""Test the brand agent system — schema validation, hard gates, artefact storage, routing.

Run with: python test_brand_system.py
No external API calls needed — all tests use mock data.
"""
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
load_dotenv(str(env_path))

# ─── Test helpers ──────────────────────────────────────────────────────────────

passed = 0
failed = 0
errors = []


def test(name: str):
    """Decorator to register and run a test."""
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  ✗ {name}: {e}")
        except Exception as e:
            failed += 1
            errors.append((name, f"Unexpected: {e}"))
            print(f"  ✗ {name}: Unexpected error: {e}")
        return fn
    return decorator


def make_valid_profile(**overrides) -> dict:
    """Create a minimal valid brand profile for testing."""
    profile = {
        "schema_version": "1.0",
        "client_id": "test-client",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
        "mode": "bold",
        "positioning": {
            "one_line": "We build things that matter",
            "enemy": "Corporate AI theatre — adopting AI to write Jira stories faster",
            "refusal": "Never use the word 'journey' or 'curated'",
            "audience_filter": "Middle managers who want process over outcomes",
        },
        "naming": {
            "name": "TestBrand",
            "rationale": "The founder said they wanted something that sounds like a declaration, not a description. This name came from their exact phrasing during the interview.",
            "verification": {
                "web_checked": True,
                "trademark_checked": True,
                "linguistic_checked": True,
                "collisions": [],
            },
        },
        "voice": {
            "descriptors": ["provocative", "direct", "assertive"],
            "casing": "sentence",
            "sentence_feel": "Short, declarative, punchy. No subordinate clauses. Every sentence is a statement.",
            "person": "first-person singular",
            "banned_words": ["crafted", "elevate", "curated", "journey", "solutions", "leverage"],
            "signature_phrases": ["You spent 15 years getting good. Now start over."],
            "example_on_brand": "AI theatre is what happens when product managers adopt AI to write Jira stories faster.",
            "example_off_brand": "We leverage cutting-edge AI solutions to curate elevated customer journeys.",
        },
        "typography": {
            "primary": {
                "family": "Space Grotesk",
                "role": "display",
                "rationale": "The founder's all-caps manifesto style needs a geometric grotesk that carries weight at large sizes without feeling corporate. Space Grotesk has the right edge.",
                "webfont_url": "",
                "license": "OFL",
            },
            "secondary": {
                "family": "Inter",
                "role": "body",
                "rationale": "Body text needs to be legible and quiet so the display type can be loud. Inter is invisible — exactly what we need for the supporting role.",
                "webfont_url": "",
                "license": "OFL",
            },
            "pairing_logic": "Space Grotesk carries the personality; Inter stays out of the way. The contrast is weight and presence, not style.",
            "scale": {"base_px": 16, "ratio": 1.25},
        },
        "color": {
            "base": "#0A0A0A",
            "primaries": ["#FFFFFF", "#FF0000"],
            "accent": "#FF0000",
            "warm_dark": "#1A1A1A",
            "warm_light": "#F5F5F5",
            "rationale": "Black and white with a single red accent. The founder said 'I want people to feel uncomfortable, not cozy.' High contrast, no warmth, no compromise.",
            "contrast_checked": True,
        },
        "texture_and_grade": {
            "texture": ["none — clean, stark, editorial"],
            "photo_grade": {
                "temperature": "neutral",
                "saturation": "desaturated except accent",
                "grain": "none",
                "retouching": "minimal",
            },
        },
        "logo_concept": {
            "metaphor": "A stamp of authority — like a newspaper masthead crossed with a warning label",
            "form_language": "wordmark",
            "construction": "Bold uppercase wordmark in Space Grotesk, with the accent color applied to a single letter or punctuation mark",
            "constraints": ["single-color version required", "legible at 12px"],
            "rationale": "The founder's manifesto approach demands a wordmark, not a symbol. The brand IS the name, stated loudly.",
        },
        "exclusion_list": {
            "category_conventions_banned": [
                "geometric sans + sage green",
                "the word 'crafted'",
                "soft gradients",
                "illustration of people shaking hands",
                "corporate blue palette",
            ],
            "source": "Phase 2 convention mapping of product management and AI consulting space",
        },
        "seo_constraints": {
            "voice_is_hard_constraint": True,
            "headlines_must_be_real_text": True,
        },
        "provenance": {
            "interview_specifics_used": [
                "The founder said: 'AI theatre is what happens when PMs adopt AI to write Jira stories faster'",
                "The founder refuses to work with middle managers who want process over outcomes",
                "The founder's manifesto uses all-caps and short punchy sentences as a deliberate choice",
            ],
            "distant_wells_mined": [
                "punk zine typography",
                "newspaper masthead design",
                "protest poster lettering",
            ],
        },
    }
    # Apply overrides
    for key, value in overrides.items():
        if isinstance(value, dict) and key in profile and isinstance(profile[key], dict):
            profile[key].update(value)
        else:
            profile[key] = value
    return profile


# ─── Tests ─────────────────────────────────────────────────────────────────────

print("=" * 80)
print("BRAND AGENT SYSTEM TESTS")
print("=" * 80)

# ─── 1. Schema validation ─────────────────────────────────────────────────────

print("\n1. Schema Validation")

@test("Valid profile passes schema validation")
def _():
    from src.brand_validator import validate_schema
    profile = make_valid_profile()
    violations = validate_schema(profile)
    assert violations == [], f"Expected no violations, got: {violations}"


@test("Valid profile passes hard gate validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    violations = validate_hard_gates(profile)
    assert violations == [], f"Expected no violations, got: {violations}"


@test("Valid profile passes full validation")
def _():
    from src.brand_validator import validate_brand_profile
    profile = make_valid_profile()
    violations = validate_brand_profile(profile)
    assert violations == [], f"Expected no violations, got: {violations}"


# ─── 2. Hard gate rejection ───────────────────────────────────────────────────

print("\n2. Hard Gate Rejection")

@test("Empty rationale fails validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["naming"]["rationale"] = ""
    violations = validate_hard_gates(profile)
    assert any("rationale" in v.lower() for v in violations), f"Expected rationale violation, got: {violations}"


@test("Short rationale fails validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["naming"]["rationale"] = "short"
    violations = validate_hard_gates(profile)
    assert any("rationale" in v.lower() for v in violations), f"Expected rationale violation, got: {violations}"


@test("Fewer than 3 interview specifics fails")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["provenance"]["interview_specifics_used"] = ["only one specific"]
    violations = validate_hard_gates(profile)
    assert any("interview_specifics" in v for v in violations), f"Expected provenance violation, got: {violations}"


@test("web_checked false fails validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["naming"]["verification"]["web_checked"] = False
    violations = validate_hard_gates(profile)
    assert any("web_checked" in v for v in violations), f"Expected verification violation, got: {violations}"


@test("contrast_checked false fails validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["color"]["contrast_checked"] = False
    violations = validate_hard_gates(profile)
    assert any("contrast" in v for v in violations), f"Expected contrast violation, got: {violations}"


@test("Empty exclusion list fails validation")
def _():
    from src.brand_validator import validate_hard_gates
    profile = make_valid_profile()
    profile["exclusion_list"]["category_conventions_banned"] = []
    violations = validate_hard_gates(profile)
    assert any("exclusion" in v.lower() for v in violations), f"Expected exclusion violation, got: {violations}"


# ─── 3. Artefact storage ──────────────────────────────────────────────────────

print("\n3. Artefact Storage")

@test("write_profile creates brand-profile.json in artefacts")
def _():
    from src.brand_tools import write_profile
    from src import memory

    profile = make_valid_profile()
    result = write_profile("test-storage", profile)

    assert result["status"] == "success", f"Expected success, got: {result}"

    profile_path = Path(result["profile_path"])
    assert profile_path.exists(), f"Profile file not created: {profile_path}"

    written = json.loads(profile_path.read_text(encoding="utf-8"))
    assert written["client_id"] == "test-storage"
    assert written["mode"] == "bold"

    # Cleanup
    profile_path.unlink()


@test("write_profile creates brand-constraints.md on blackboard")
def _():
    from src.brand_tools import write_profile
    from src import memory

    profile = make_valid_profile()
    result = write_profile("test-constraints", profile)
    assert result["status"] == "success"

    constraints_path = memory._get_memory_dir() / "brand-constraints.md"
    assert constraints_path.exists(), f"Constraints file not created: {constraints_path}"

    content = constraints_path.read_text(encoding="utf-8")
    assert "Brand Constraints" in content
    assert "Banned words" in content
    assert "crafted" in content
    assert "sentence" in content

    # Cleanup
    constraints_path.unlink()


@test("write_profile indexes in artefacts-index.md")
def _():
    from src.brand_tools import write_profile
    from src import memory

    # Read current index
    index_path = memory._get_memory_dir() / "artefacts-index.md"
    before = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    profile = make_valid_profile()
    result = write_profile("test-index", profile)
    assert result["status"] == "success"

    after = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    assert "test-index-brand-profile" in after, "Artefact not indexed"

    # Restore original index
    index_path.write_text(before, encoding="utf-8")

    # Cleanup artefact
    artefact_path = memory._get_memory_dir() / "artefacts" / "test-index-brand-profile.json"
    if artefact_path.exists():
        artefact_path.unlink()


# ─── 4. Memory integration ─────────────────────────────────────────────────────

print("\n4. Memory Integration")

@test("read_brand_constraints returns empty when no file exists")
def _():
    from src import memory

    constraints_path = memory._get_memory_dir() / "brand-constraints.md"
    existed = constraints_path.exists()

    if existed:
        # Temporarily rename
        backup = constraints_path.with_suffix(".md.bak")
        constraints_path.rename(backup)

    try:
        result = memory.read_brand_constraints()
        assert result == "", f"Expected empty string, got: {result[:100]}"
    finally:
        if existed:
            backup.rename(constraints_path)


@test("read_brand_constraints returns content when file exists")
def _():
    from src import memory

    constraints_path = memory._get_memory_dir() / "brand-constraints.md"
    backup = None
    if constraints_path.exists():
        backup = constraints_path.with_suffix(".md.bak")
        constraints_path.rename(backup)

    try:
        constraints_path.write_text("# Brand Constraints\nTest content", encoding="utf-8")
        result = memory.read_brand_constraints()
        assert "Test content" in result
    finally:
        constraints_path.unlink()
        if backup:
            backup.rename(constraints_path)


# ─── 5. Orchestrator routing ───────────────────────────────────────────────────

print("\n5. Orchestrator Routing")

@test("orchestrator has brand_agent in AGENT_REGISTRY")
def _():
    from src.orchestrator import AGENT_REGISTRY
    assert "brand_agent" in AGENT_REGISTRY, f"brand_agent not in registry: {list(AGENT_REGISTRY.keys())}"
    assert AGENT_REGISTRY["brand_agent"]["handler"] is not None


@test("orchestrator system prompt mentions Brand Agent")
def _():
    from src.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
    assert "Brand Agent" in ORCHESTRATOR_SYSTEM_PROMPT, "Brand Agent not mentioned in system prompt"


@test("brand_agent module imports correctly")
def _():
    from src.brand_agent import run_brand_agent, TOOL_DEFINITIONS, TOOL_CALLABLES
    assert callable(run_brand_agent)
    assert len(TOOL_DEFINITIONS) > 0
    assert "write_profile" in TOOL_CALLABLES
    assert "fetch_url" in TOOL_CALLABLES
    assert "trademark_lookup" in TOOL_CALLABLES
    assert "font_pairing" in TOOL_CALLABLES
    assert "color_system" in TOOL_CALLABLES


@test("brand_tools fetch_url handles errors gracefully")
def _():
    from src.brand_tools import fetch_url
    result = fetch_url("https://this-domain-does-not-exist-12345.com")
    assert "error" in result or result.get("status") == 0, f"Expected error, got: {result}"


# ─── Summary ───────────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 80)

if errors:
    print("\nFailed tests:")
    for name, error in errors:
        print(f"  ✗ {name}: {error}")

sys.exit(0 if failed == 0 else 1)
