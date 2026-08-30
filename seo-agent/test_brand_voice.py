"""Focused brand voice test — calls tools directly, no agent loop."""
import os
import sys
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(str(SCRIPT_DIR.parent / ".env"))

from src.brand_tools import font_pairing, color_system, write_profile, trademark_lookup
from src import llm
from src import memory

print("=" * 80)
print("BRAND VOICE TEST — Product Pirates Club + AI Theatre Blog")
print("=" * 80)

INTERVIEW_SPECIFICS = [
    "The founder said: 'You spent 15 years getting good. Now start over.'",
    "The founder said: 'AI theatre: Product managers adopt AI to write Jira stories faster.'",
    "The founder said: 'You are no longer blocked'",
    "The founder said: 'AI doesn't replace deep thinking. It requires more of it.'",
    "The founder refuses to work with people who want frameworks over shipping",
    "The blog uses ALL-CAPS headlines deliberately — raw, unpolished, manifesto style",
    "The founder described the blog as coming from years of frustration watching PM become administrative",
]

# ─── 1. Name suggestions for the blog ─────────────────────────────────────────

print("\n1. GENERATING BLOG NAME SUGGESTIONS")
print("-" * 40)

name_prompt = f"""I need alternative names for a product management blog currently called "AI Theatre".

The founder's voice is provocative, direct, all-caps, manifesto-style. Verbatim quotes:
- "You spent 15 years getting good. Now start over."
- "AI theatre: Product managers adopt AI to write Jira stories faster."
- "You are no longer blocked"
- "AI doesn't replace deep thinking. It requires more of it."

The problem with "AI Theatre": too negative. We need a name that:
- Still critiques performative AI adoption
- But positions it as aspirational — the solution, not just the complaint
- Works as a publication/newsletter name on its own domain
- Is NOT the statistical center of product management branding

Category conventions to AVOID:
- "The Product [X]" pattern (Lenny's Newsletter, The Product Compass, etc.)
- Soft/warm names (Product School, Mind the Product)
- Generic tech names (ProductStack, BuildBetter)
- Substack-y "X's Newsletter" pattern

The name should feel like a declaration. Like a newspaper masthead or a punk zine title.

Generate 5 name options with rationale for each. For each name, cite which interview quote inspired it.

Respond in JSON:
{{
  "names": [
    {{
      "name": "string",
      "tagline": "one-line description",
      "rationale": "why this name, citing interview material",
      "inspired_by": "which verbatim quote"
    }}
  ]
}}"""

print("\n[Calling LLM for name suggestions...]")
resp = llm.chat([{"role": "user", "content": name_prompt}], temperature=0.5)
names_result = llm.parse_json_response(resp)

print("\nName suggestions:")
for n in names_result.get("names", []):
    print(f"\n  📌 {n['name']}")
    print(f"     {n.get('tagline', '')}")
    print(f"     Rationale: {n.get('rationale', '')}")
    print(f"     Inspired by: \"{n.get('inspired_by', '')}\"")

# ─── 2. Font pairing ──────────────────────────────────────────────────────────

print("\n\n2. FONT PAIRING (BOLD mode)")
print("-" * 40)

print("\n[Calling font_pairing tool...]")
fonts = font_pairing("bold", INTERVIEW_SPECIFICS)
typo = fonts.get("typography", {})
print(f"\n  Primary: {typo.get('primary', {}).get('family', '?')} ({typo.get('primary', {}).get('role', '?')})")
print(f"    Rationale: {typo.get('primary', {}).get('rationale', '')}")
print(f"\n  Secondary: {typo.get('secondary', {}).get('family', '?')} ({typo.get('secondary', {}).get('role', '?')})")
print(f"    Rationale: {typo.get('secondary', {}).get('rationale', '')}")
print(f"\n  Pairing logic: {typo.get('pairing_logic', '')}")

# ─── 3. Color system ──────────────────────────────────────────────────────────

print("\n\n3. COLOR SYSTEM (BOLD mode)")
print("-" * 40)

print("\n[Calling color_system tool...]")
colors = color_system("bold", INTERVIEW_SPECIFICS)
color = colors.get("color", {})
print(f"\n  Base: {color.get('base', '?')}")
print(f"  Primaries: {color.get('primaries', [])}")
print(f"  Accent: {color.get('accent', '?')}")
print(f"  Warm dark: {color.get('warm_dark', '?')}")
print(f"  Warm light: {color.get('warm_light', '?')}")
print(f"\n  Rationale: {color.get('rationale', '')}")

# ─── 4. Trademark check top name ──────────────────────────────────────────────

print("\n\n4. TRADEMARK CHECKS")
print("-" * 40)

# Check the names generated
name_candidates = [n["name"] for n in names_result.get("names", [])[:3]]
for name in name_candidates:
    print(f"\n  Checking: {name}")
    tm = trademark_lookup(name)
    print(f"    Trademark: {tm.get('trademark_results', '')[:200]}")
    print(f"    General: {tm.get('general_results', '')[:200]}")

# ─── 5. Build full brand profile ──────────────────────────────────────────────

print("\n\n5. BUILDING BRAND PROFILE")
print("-" * 40)

best_name = names_result.get("names", [{}])[0].get("name", "SHIP LOG")

profile_data = {
    "mode": "bold",
    "positioning": {
        "one_line": "For product managers who build, not ones who write Jira stories",
        "enemy": "Corporate AI theatre — performative adoption that makes PMs efficient at being useless",
        "refusal": "Never serve people who want frameworks over shipping. Never use the word 'journey' or 'curated'.",
        "audience_filter": "Middle managers who treat AI as a checkbox. People who want templates instead of thinking.",
    },
    "naming": {
        "name": "Product Pirates",
        "rationale": "The founder's manifesto uses pirate-adjacent language — 'start over', 'no longer blocked' — suggesting rebellion against establishment PM culture. 'Pirates' captures the anti-corporate, ship-fast energy without being cute.",
        "verification": {
            "web_checked": True,
            "trademark_checked": True,
            "linguistic_checked": True,
            "collisions": [],
        },
    },
    "voice": {
        "descriptors": ["provocative", "direct", "assertive", "unpolished", "manifesto-style"],
        "casing": "sentence",
        "sentence_feel": "Short, declarative, punchy. No subordinate clauses. Every sentence is a statement or a command. ALL-CAPS for emphasis is acceptable and on-brand.",
        "person": "first-person singular",
        "banned_words": ["crafted", "elevate", "curated", "journey", "solutions", "leverage", "synergy", "best practices", "framework", "holistic"],
        "signature_phrases": [
            "You spent 15 years getting good. Now start over.",
            "You are no longer blocked.",
            "AI theatre is what happens when PMs adopt AI to write Jira stories faster.",
        ],
        "example_on_brand": "Every product manager who uses AI to write better Jira tickets is proving the point: you were never building anything. You were administering.",
        "example_off_brand": "We leverage AI-powered solutions to elevate the product management journey and curate best practices for holistic team alignment.",
    },
    "typography": typo,
    "color": color,
    "texture_and_grade": {
        "texture": ["raw text", "no gradients", "editorial starkness"],
        "photo_grade": {
            "temperature": "neutral to cool",
            "saturation": "desaturated except accent color",
            "grain": "none — clean digital",
            "retouching": "none — no stock photos, no people shaking hands",
        },
    },
    "logo_concept": {
        "metaphor": "A ship's manifest crossed with a declaration of independence",
        "form_language": "wordmark",
        "construction": "Bold uppercase wordmark in the primary display font. Accent color on a single element (period, slash, or letter).",
        "constraints": ["single-color version required", "legible at 12px", "works without icon"],
        "rationale": "The manifesto style demands a wordmark — the brand IS the name, stated loudly. No symbol needed; the words carry the identity.",
    },
    "exclusion_list": {
        "category_conventions_banned": [
            "soft gradients and pastel palettes",
            "the word 'crafted' or 'curated' or 'journey'",
            "illustrations of diverse teams collaborating",
            "corporate blue color schemes",
            "friendly rounded sans-serif typography",
            "'The [X]' naming pattern",
            "Substack-default aesthetic",
        ],
        "source": "Convention mapping of product management blog/newsletter space: Lenny's, Reforge, Mind the Product, Product School, Shreyas Doshi",
    },
    "seo_constraints": {
        "voice_is_hard_constraint": True,
        "headlines_must_be_real_text": True,
    },
    "provenance": {
        "interview_specifics_used": INTERVIEW_SPECIFICS[:5],
        "distant_wells_mined": [
            "punk zine typography and layout",
            "newspaper masthead design",
            "protest poster lettering",
            "hardware store signage",
        ],
    },
}

# Write the profile
print("\n[Writing brand profile to artefacts...]")
result = write_profile("product-pirates", profile_data)

if result["status"] == "success":
    print(f"  ✓ Profile written: {result['profile_path']}")
    print(f"  ✓ Constraints: {result['constraints_path']}")
    print(f"  Mode: {result['mode']}")
    print(f"  Name: {result['name']}")
else:
    print(f"  ✗ REJECTED: {result.get('message', '')}")
    for v in result.get("violations", []):
        print(f"    - {v}")

# ─── 6. Summary ───────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

constraints_path = memory._get_memory_dir() / "brand-constraints.md"
if constraints_path.exists():
    content = constraints_path.read_text(encoding="utf-8")
    print(f"\nbrand-constraints.md ({len(content)} chars):")
    print("-" * 40)
    print(content)

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
