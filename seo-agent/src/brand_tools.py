"""Brand agent tools — interview, research, and profile emission."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import memory
from . import llm
from .brand_validator import validate_brand_profile

AGENT_NAME = "brand-agent"


def fetch_url(url: str) -> dict[str, Any]:
    """Fetch raw content from a URL for competitor/site analysis.

    Distinct from web_search — this fetches the full page content of a
    specific known URL, not search results for a query.
    """
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BrandAgent/1.0)"})
            resp.raise_for_status()

        html = resp.text
        # Extract text content (strip tags for readability)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = html[:5000]

        # Truncate to manageable size
        if len(text) > 8000:
            text = text[:8000] + "\n...[truncated]"

        return {
            "url": url,
            "status": resp.status_code,
            "content": text,
            "content_length": len(text),
        }
    except httpx.HTTPError as e:
        return {"url": url, "error": str(e), "status": 0}
    except Exception as e:
        return {"url": url, "error": str(e), "status": 0}


def trademark_lookup(name: str) -> dict[str, Any]:
    """Check for trademark/name conflicts via web search."""
    # Use the same web_search pattern as the SEO agent
    from .tools.web_search import web_search

    results = web_search(f'"{name}" trademark registration site:uspto.gov OR site:euipo.europa.eu OR site:wipo.int')
    general = web_search(f'"{name}" brand company')

    return {
        "name": name,
        "trademark_results": results.get("results", ""),
        "general_results": general.get("results", ""),
        "note": "Review results for conflicts. Check linguistic meaning in target markets manually.",
    }


def write_profile(client_id: str, profile_data: dict[str, Any] | str) -> dict[str, Any]:
    """Validate and emit brand_profile.json + brand-constraints.md.

    Hard gates enforced before writing:
    - Schema validation passes
    - All rationale fields non-empty
    - Naming verification all true
    - ≥3 interview specifics
    - Contrast checked
    - Non-empty exclusion list
    """
    # Handle JSON string input (LLM sometimes passes profile_data as string)
    if isinstance(profile_data, str):
        try:
            profile_data = json.loads(profile_data)
        except json.JSONDecodeError as e:
            return {"status": "rejected", "message": f"profile_data must be valid JSON dict: {e}"}
    
    if not isinstance(profile_data, dict):
        return {"status": "rejected", "message": f"profile_data must be a dict, got {type(profile_data).__name__}"}
    
    # Set metadata
    profile_data["schema_version"] = profile_data.get("schema_version", "1.0")
    profile_data["client_id"] = client_id
    profile_data["generated_at"] = datetime.now(timezone.utc).isoformat()
    profile_data["status"] = profile_data.get("status", "draft")

    # Validate
    violations = validate_brand_profile(profile_data)
    if violations:
        return {
            "status": "rejected",
            "violations": violations,
            "message": f"Profile failed {len(violations)} validation check(s). Fix and retry.",
        }

    # Write brand-profile.json to artefacts
    memory_dir = memory._get_memory_dir()
    artefacts_dir = memory_dir / "artefacts"
    artefacts_dir.mkdir(exist_ok=True)

    profile_path = artefacts_dir / f"{client_id}-brand-profile.json"
    profile_path.write_text(
        json.dumps(profile_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # Write brand-constraints.md to blackboard
    _write_brand_constraints(profile_data, memory_dir)

    # Index in artefacts-index.md
    mode = profile_data.get("mode", "unknown")
    name = profile_data.get("naming", {}).get("name", client_id)
    summary = f"Brand identity profile ({mode} mode) for {name}"
    location = f"agent-memory/artefacts/{client_id}-brand-profile.json"
    memory.record_artefact(f"{client_id}-brand-profile", summary, location)

    # Record decision in blackboard
    memory.record_decision(
        f"Brand profile created for {name} ({mode} mode)",
        agent=AGENT_NAME,
    )

    return {
        "status": "success",
        "profile_path": str(profile_path),
        "constraints_path": str(memory_dir / "brand-constraints.md"),
        "client_id": client_id,
        "mode": mode,
        "name": name,
    }


def _write_brand_constraints(profile: dict[str, Any], memory_dir: Path) -> None:
    """Extract voice/style constraints from profile and write to blackboard."""
    voice = profile.get("voice", {})
    positioning = profile.get("positioning", {})
    naming = profile.get("naming", {})
    exclusion = profile.get("exclusion_list", {})

    lines = [
        "# Brand Constraints",
        "",
        f"**Client:** {naming.get('name', 'unknown')}",
        f"**Mode:** {profile.get('mode', 'unknown')}",
        f"**Generated:** {profile.get('generated_at', 'unknown')}",
        "",
        "## Voice (HARD CONSTRAINT — do not violate)",
        "",
        f"- **Descriptors:** {', '.join(voice.get('descriptors', []))}",
        f"- **Casing:** {voice.get('casing', 'sentence')}",
        f"- **Sentence feel:** {voice.get('sentence_feel', '')}",
        f"- **Person:** {voice.get('person', 'none')}",
        "",
        "### Banned words (never use these)",
        "",
    ]

    for word in voice.get("banned_words", []):
        lines.append(f"- {word}")

    lines.extend([
        "",
        "### Signature phrases (use freely)",
        "",
    ])

    for phrase in voice.get("signature_phrases", []):
        lines.append(f"- \"{phrase}\"")

    lines.extend([
        "",
        "### On-brand example",
        "",
        f"> {voice.get('example_on_brand', '')}",
        "",
        "### Off-brand example (never write like this)",
        "",
        f"> {voice.get('example_off_brand', '')}",
        "",
        "## Positioning",
        "",
        f"- **One line:** {positioning.get('one_line', '')}",
        f"- **Enemy:** {positioning.get('enemy', '')}",
        f"- **Refusal:** {positioning.get('refusal', '')}",
        f"- **Excludes:** {positioning.get('audience_filter', '')}",
        "",
        "## Exclusions (category conventions to avoid)",
        "",
    ])

    for item in exclusion.get("category_conventions_banned", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## SEO constraints",
        "",
        "- Voice is a HARD CONSTRAINT on all copy",
        "- Headlines must be real text (never baked into images)",
        "",
    ])

    constraints_path = memory_dir / "brand-constraints.md"
    constraints_path.write_text("\n".join(lines), encoding="utf-8")


def font_pairing(mode: str, interview_specifics: list[str]) -> dict[str, Any]:
    """Select typography pairing based on brand mode and interview material.

    Args:
        mode: "handmade" or "bold"
        interview_specifics: Verbatim quotes from founder interview
    """
    specifics_text = "\n".join(f"- {s}" for s in interview_specifics)

    prompt = f"""Based on these founder interview specifics:
{specifics_text}

And brand mode: {mode}

Recommend a typography pairing (primary display font + secondary body font).

Rules:
- The pairing must be traceable to specific interview material
- Avoid category defaults (no geometric sans + clean sans for tech, no soft serif for lifestyle)
- Consider texture, weight contrast, and personality
- Both fonts must be available as web fonts (Google Fonts, Adobe Fonts, or similar)
- Provide rationale for each choice citing the interview material

Respond in JSON:
{{
  "primary": {{
    "family": "font name",
    "role": "display",
    "rationale": "why this font, citing interview material",
    "webfont_url": "url or empty string",
    "license": "license type"
  }},
  "secondary": {{
    "family": "font name",
    "role": "body",
    "rationale": "why this font, citing interview material",
    "webfont_url": "url or empty string",
    "license": "license type"
  }},
  "pairing_logic": "why the contrast works",
  "scale": {{
    "base_px": 16,
    "ratio": 1.25
  }}
}}"""

    resp = llm.chat([{"role": "user", "content": prompt}], temperature=0.4)
    result = llm.parse_json_response(resp)

    return {"typography": result, "mode": mode}


def color_system(mode: str, interview_specifics: list[str]) -> dict[str, Any]:
    """Generate color palette from interview material with contrast checking.

    Args:
        mode: "handmade" or "bold"
        interview_specifics: Verbatim quotes from founder interview
    """
    specifics_text = "\n".join(f"- {s}" for s in interview_specifics)

    mode_guidance = {
        "handmade": "Earthy, desaturated, warm. Think aged paper, natural materials, muted pigments.",
        "bold": "High contrast, one polarizing accent. Think editorial, gallery, nightclub.",
    }

    prompt = f"""Based on these founder interview specifics:
{specifics_text}

Brand mode: {mode}
Mode guidance: {mode_guidance.get(mode, "")}

Create a color palette. Rules:
- Must be traceable to specific interview material
- Avoid category defaults (no sage green for wellness, no corporate blue for tech)
- All hex values must be valid (#RRGGBB)
- Check WCAG AA contrast: text on base must pass 4.5:1 minimum
- Provide rationale citing interview material

Respond in JSON:
{{
  "base": "#hex",
  "primaries": ["#hex", "#hex"],
  "accent": "#hex",
  "warm_dark": "#hex",
  "warm_light": "#hex",
  "rationale": "why this palette, citing interview material",
  "contrast_checked": true,
  "contrast_notes": "which pairs pass AA"
}}"""

    resp = llm.chat([{"role": "user", "content": prompt}], temperature=0.4)
    result = llm.parse_json_response(resp)

    # Remove contrast_notes (not in schema, just for review)
    result.pop("contrast_notes", None)

    return {"color": result, "mode": mode}
