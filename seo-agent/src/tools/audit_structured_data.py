from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from ..config import settings


def _summarize(checks: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return counts


_GOOGLE_SUPPORTED_TYPES = {
    "Article", "BreadcrumbList", "Course", "Event", "FAQPage", "HowTo",
    "ImageObject", "JobPosting", "LocalBusiness", "Organization", "Person",
    "Product", "ProductGroup", "Recipe", "Review", "SoftwareApplication",
    "VideoObject", "WebSite", "SpeakableSpecification",
}

_REQUIRED_PROPERTIES: dict[str, list[str]] = {
    "Article": ["headline", "author", "datePublished"],
    "Product": ["name", "image"],
    "Review": ["itemReviewed", "reviewRating", "author"],
    "LocalBusiness": ["name", "image", "address"],
    "Recipe": ["name", "image"],
    "Event": ["name", "startDate", "location"],
    "BreadcrumbList": ["itemListElement"],
    "Organization": ["name", "url"],
}

_RECOMMENDED_PROPERTIES: dict[str, list[str]] = {
    "Article": ["dateModified", "publisher", "mainEntityOfPage"],
    "Product": ["offers", "aggregateRating", "review"],
    "Recipe": ["cookTime", "prepTime", "recipeIngredient", "recipeInstructions"],
}


def _extract_schemas(soup: BeautifulSoup) -> tuple[list[dict], bool]:
    """Return (list of parsed schema dicts, all_valid flag)."""
    schemas: list[dict] = []
    all_valid = True
    for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(block.string)
            if isinstance(data, list):
                schemas.extend(data)
            elif isinstance(data, dict):
                # Handle @graph wrapper
                if "@graph" in data:
                    schemas.extend(data["@graph"])
                else:
                    schemas.append(data)
        except (json.JSONDecodeError, TypeError):
            all_valid = False
    return schemas, all_valid


def _has_property(schema: dict, prop: str) -> bool:
    """Check if a schema has a given property (supports dotted paths like offers.price)."""
    parts = prop.split(".")
    current = schema
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return True


def audit_structured_data(url: str) -> dict:
    """Run structured-data audit (E1–E9) on the given URL."""
    if not url.startswith("http"):
        url = f"https://{url}"

    checks: list[dict] = []

    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "SEOAgent/1.0"},
    ) as client:
        resp = client.get(url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        jsonld_blocks = soup.find_all("script", attrs={"type": "application/ld+json"})
        microdata_items = soup.find_all(attrs={"itemscope": True})
        schemas, all_valid = _extract_schemas(soup)

        types_found: list[str] = []
        for s in schemas:
            if isinstance(s, dict) and "@type" in s:
                t = s["@type"]
                if isinstance(t, list):
                    types_found.extend(t)
                else:
                    types_found.append(t)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_types: list[str] = []
        for t in types_found:
            if t not in seen:
                seen.add(t)
                unique_types.append(t)
        types_found = unique_types

        # ── E1: Schema present ────────────────────────────────────
        has_schema = bool(jsonld_blocks) or bool(microdata_items)
        checks.append({
            "id": "E1", "category": "Schema", "title": "Schema Present",
            "status": "pass" if has_schema else "warn",
            "detail": (
                f"Found {len(jsonld_blocks)} JSON-LD blocks, {len(microdata_items)} microdata items"
                if has_schema else "No structured data detected"
            ),
        })

        # ── E2: Schema types found ───────────────────────────────
        if types_found:
            checks.append({
                "id": "E2", "category": "Schema", "title": "Schema Types Found",
                "status": "pass",
                "detail": f"Types: {', '.join(types_found)}",
            })
        else:
            checks.append({
                "id": "E2", "category": "Schema", "title": "Schema Types Found",
                "status": "warn",
                "detail": "Could not determine schema @type",
            })

        # ── E3: Valid JSON ────────────────────────────────────────
        checks.append({
            "id": "E3", "category": "Schema", "title": "Valid JSON",
            "status": "pass" if all_valid else "fail",
            "detail": "All JSON-LD blocks parse correctly" if all_valid else "Some JSON-LD blocks have syntax errors",
        })

        # ── E4: Google-supported types ───────────────────────────
        if types_found:
            unsupported = [t for t in types_found if t not in _GOOGLE_SUPPORTED_TYPES]
            supported = [t for t in types_found if t in _GOOGLE_SUPPORTED_TYPES]
            if unsupported:
                checks.append({
                    "id": "E4", "category": "Schema", "title": "Google-Supported Types",
                    "status": "warn",
                    "detail": (
                        f"Supported: {', '.join(supported) or 'none'}; "
                        f"Unsupported (may be ignored): {', '.join(unsupported)}"
                    ),
                })
            else:
                checks.append({
                    "id": "E4", "category": "Schema", "title": "Google-Supported Types",
                    "status": "pass",
                    "detail": f"All types Google-supported: {', '.join(supported)}",
                })
        else:
            checks.append({
                "id": "E4", "category": "Schema", "title": "Google-Supported Types",
                "status": "skip",
                "detail": "No schema types to check",
            })

        # ── E5: Required properties ──────────────────────────────
        required_issues: list[str] = []
        for s in schemas:
            if not isinstance(s, dict):
                continue
            stype = s.get("@type", "")
            if isinstance(stype, list):
                stype_list = stype
            else:
                stype_list = [stype]
            for t in stype_list:
                if t in _REQUIRED_PROPERTIES:
                    for prop in _REQUIRED_PROPERTIES[t]:
                        if not _has_property(s, prop):
                            required_issues.append(f"{t} missing '{prop}'")

        if required_issues:
            checks.append({
                "id": "E5", "category": "Schema", "title": "Required Properties",
                "status": "fail",
                "detail": "; ".join(required_issues),
            })
        else:
            checks.append({
                "id": "E5", "category": "Schema", "title": "Required Properties",
                "status": "pass",
                "detail": "All required properties present for detected types",
            })

        # ── E6: Recommended properties ───────────────────────────
        recommended_issues: list[str] = []
        for s in schemas:
            if not isinstance(s, dict):
                continue
            stype = s.get("@type", "")
            if isinstance(stype, list):
                stype_list = stype
            else:
                stype_list = [stype]
            for t in stype_list:
                if t in _RECOMMENDED_PROPERTIES:
                    for prop in _RECOMMENDED_PROPERTIES[t]:
                        if not _has_property(s, prop):
                            recommended_issues.append(f"{t} missing recommended '{prop}'")

        if recommended_issues:
            checks.append({
                "id": "E6", "category": "Schema", "title": "Recommended Properties",
                "status": "warn",
                "detail": "; ".join(recommended_issues),
            })
        else:
            checks.append({
                "id": "E6", "category": "Schema", "title": "Recommended Properties",
                "status": "pass",
                "detail": "All recommended properties present",
            })

        # ── E7: Deprecated types ─────────────────────────────────
        if "FAQPage" in types_found:
            checks.append({
                "id": "E7", "category": "Schema", "title": "Deprecated Types",
                "status": "warn",
                "detail": (
                    "FAQPage schema detected — Google now restricts rich results "
                    "for FAQPage to government and health sites only"
                ),
            })
        else:
            checks.append({
                "id": "E7", "category": "Schema", "title": "Deprecated Types",
                "status": "pass",
                "detail": "No deprecated/restricted schema types found",
            })

        # ── E8: Multiple schemas ─────────────────────────────────
        if len(types_found) > 1:
            has_product_group = "ProductGroup" in types_found
            conflicting = False
            conflict_detail: list[str] = []
            if "Article" in types_found and "Product" in types_found and not has_product_group:
                conflicting = True
                conflict_detail.append("Article + Product without ProductGroup")
            if "Review" in types_found and "Product" in types_found:
                # Review + Product is fine if review is about the product
                pass
            if conflicting:
                checks.append({
                    "id": "E8", "category": "Schema", "title": "Multiple Schemas",
                    "status": "warn",
                    "detail": f"Potentially conflicting schemas: {'; '.join(conflict_detail)}",
                })
            else:
                checks.append({
                    "id": "E8", "category": "Schema", "title": "Multiple Schemas",
                    "status": "pass",
                    "detail": f"Multiple schemas ({', '.join(types_found)}) — no conflicts detected",
                })
        else:
            checks.append({
                "id": "E8", "category": "Schema", "title": "Multiple Schemas",
                "status": "pass",
                "detail": "Single schema type — no conflict risk",
            })

        # ── E9: Image requirements ───────────────────────────────
        image_issues: list[str] = []
        for s in schemas:
            if not isinstance(s, dict):
                continue
            stype = s.get("@type", "")
            img = s.get("image")
            if stype == "Article" and img:
                # Google recommends 1200px min width for Article images
                if isinstance(img, str):
                    image_issues.append("Article image is a URL string — cannot verify dimensions; recommend ≥1200px wide")
                elif isinstance(img, dict):
                    w = img.get("width")
                    if w and isinstance(w, (int, float)) and w < 1200:
                        image_issues.append(f"Article image width {w}px < 1200px recommended")
            if stype == "Product" and not img:
                image_issues.append("Product schema missing image property")
            if stype == "Recipe" and not img:
                image_issues.append("Recipe schema missing image property")

        if image_issues:
            checks.append({
                "id": "E9", "category": "Schema", "title": "Image Requirements",
                "status": "warn",
                "detail": "; ".join(image_issues),
            })
        else:
            checks.append({
                "id": "E9", "category": "Schema", "title": "Image Requirements",
                "status": "pass",
                "detail": "Schema images meet minimum requirements or not applicable",
            })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
        "schemas_found": types_found,
    }
