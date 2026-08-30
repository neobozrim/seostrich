"""Brand profile validator — hard gates before emit.

Validates brand_profile.json against:
1. JSON Schema (structure, types, required fields)
2. Hard gates (rationale non-empty, verification done, provenance sufficient)

Returns list of violations (empty = pass).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_LOCAL_SCHEMA = Path(__file__).resolve().parent.parent / "shared" / "schema" / "brand_profile_schema.json"
_ROOT_SCHEMA = Path(__file__).resolve().parent.parent.parent / "shared" / "schema" / "brand_profile_schema.json"
# Prefer the copy inside the deploy root; fall back to the repo-root one locally
SCHEMA_PATH = _LOCAL_SCHEMA if _LOCAL_SCHEMA.exists() else _ROOT_SCHEMA


def validate_schema(profile: dict[str, Any]) -> list[str]:
    """Validate profile against JSON Schema. Returns list of violations."""
    violations = []

    if not SCHEMA_PATH.exists():
        violations.append(f"Schema file not found: {SCHEMA_PATH}")
        return violations

    try:
        from jsonschema import validate, ValidationError, Draft7Validator
    except ImportError:
        violations.append("jsonschema package not installed — skipping schema validation")
        return violations

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(profile), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.path) or "(root)"
        violations.append(f"Schema: {path}: {error.message}")

    return violations


def validate_hard_gates(profile: dict[str, Any]) -> list[str]:
    """Check hard gates that go beyond schema validation.

    Hard gates from spec:
    - Every rationale field non-empty
    - naming.verification all true
    - ≥3 entries in provenance.interview_specifics_used
    - color.contrast_checked true
    - Non-empty exclusion_list
    """
    violations = []

    # Check all rationale fields
    _check_rationales(profile, violations)

    # Check naming verification
    naming = profile.get("naming", {})
    verification = naming.get("verification", {})
    if not verification.get("web_checked"):
        violations.append("Hard gate: naming.verification.web_checked must be true")
    if not verification.get("trademark_checked"):
        violations.append("Hard gate: naming.verification.trademark_checked must be true")
    if not verification.get("linguistic_checked"):
        violations.append("Hard gate: naming.verification.linguistic_checked must be true")

    # Check provenance
    provenance = profile.get("provenance", {})
    specifics = provenance.get("interview_specifics_used", [])
    if len(specifics) < 3:
        violations.append(
            f"Hard gate: provenance.interview_specifics_used needs ≥3 entries, has {len(specifics)}"
        )

    # Check contrast
    color = profile.get("color", {})
    if not color.get("contrast_checked"):
        violations.append("Hard gate: color.contrast_checked must be true")

    # Check exclusion list
    exclusion = profile.get("exclusion_list", {})
    banned = exclusion.get("category_conventions_banned", [])
    if not banned:
        violations.append("Hard gate: exclusion_list.category_conventions_banned must not be empty")

    return violations


def _check_rationales(obj: Any, violations: list[str], path: str = "") -> None:
    """Recursively check that all rationale fields are non-empty."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            if key == "rationale":
                if not value or not str(value).strip():
                    violations.append(f"Hard gate: {current_path} must not be empty")
                elif len(str(value).strip()) < 10:
                    violations.append(
                        f"Hard gate: {current_path} too short ({len(str(value).strip())} chars, min 10)"
                    )
            else:
                _check_rationales(value, violations, current_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_rationales(item, violations, f"{path}[{i}]")


def validate_brand_profile(profile: dict[str, Any]) -> list[str]:
    """Run all validations. Returns list of violations (empty = pass)."""
    violations = []
    violations.extend(validate_schema(profile))
    violations.extend(validate_hard_gates(profile))
    return violations
