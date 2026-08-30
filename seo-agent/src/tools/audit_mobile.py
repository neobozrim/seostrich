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


def audit_mobile(url: str) -> dict:
    """Run mobile-friendliness audit (F1–F5) on the given URL."""
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

        # ── F1: Viewport meta ─────────────────────────────────────
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if viewport and "width=device-width" in (viewport.get("content") or ""):
            status, detail = "pass", "Viewport meta tag correctly set"
        else:
            status, detail = "fail", "Missing or incorrect viewport meta tag"
        checks.append({
            "id": "F1", "category": "Mobile", "title": "Viewport",
            "status": status, "detail": detail,
        })

        # ── F2: Horizontal scroll ────────────────────────────────
        fixed_width = soup.find_all(style=re.compile(r"width:\s*\d{3,}px"))
        fixed_tables = soup.find_all("table", attrs={"width": re.compile(r"\d{3,}")})
        if fixed_width or fixed_tables:
            checks.append({
                "id": "F2", "category": "Mobile", "title": "Horizontal Scroll",
                "status": "warn",
                "detail": (
                    f"Found {len(fixed_width)} fixed-width elements and "
                    f"{len(fixed_tables)} fixed-width tables"
                ),
            })
        else:
            checks.append({
                "id": "F2", "category": "Mobile", "title": "Horizontal Scroll",
                "status": "pass", "detail": "No obvious horizontal scroll causes",
            })

        # ── F3: Touch targets ────────────────────────────────────
        small_targets: list[str] = []
        for tag in soup.find_all(["a", "button"]):
            style = tag.get("style", "")
            if style:
                # Look for small padding / height
                padding_match = re.search(r"padding\s*:\s*(\d+)px", style)
                height_match = re.search(r"height\s*:\s*(\d+)px", style)
                if padding_match and int(padding_match.group(1)) < 8:
                    small_targets.append(f"<{tag.name}> with padding {padding_match.group(1)}px")
                if height_match and int(height_match.group(1)) < 32:
                    small_targets.append(f"<{tag.name}> with height {height_match.group(1)}px (< 32px)")
            # Check for inline dimensions via width/height attrs
            width_attr = tag.get("width", "")
            height_attr = tag.get("height", "")
            if width_attr and width_attr.isdigit() and int(width_attr) < 44:
                small_targets.append(f"<{tag.name}> width={width_attr}px (< 44px min touch target)")

        if small_targets:
            checks.append({
                "id": "F3", "category": "Mobile", "title": "Touch Targets",
                "status": "warn",
                "detail": f"{len(small_targets)} interactive element(s) may have small touch targets: {small_targets[0]}" + (
                    f" (+{len(small_targets) - 1} more)" if len(small_targets) > 1 else ""
                ),
            })
        else:
            checks.append({
                "id": "F3", "category": "Mobile", "title": "Touch Targets",
                "status": "pass",
                "detail": "No obviously undersized touch targets detected in inline styles",
            })

        # ── F4: Font size ────────────────────────────────────────
        small_fonts: list[str] = []
        for tag in soup.find_all(style=True):
            style = tag.get("style", "")
            for match in re.finditer(r"font-size\s*:\s*(\d+)px", style):
                size = int(match.group(1))
                if size < 12:
                    small_fonts.append(f"<{tag.name}> font-size: {size}px")

        if small_fonts:
            checks.append({
                "id": "F4", "category": "Mobile", "title": "Font Size",
                "status": "warn",
                "detail": f"{len(small_fonts)} element(s) with inline font-size < 12px: {small_fonts[0]}" + (
                    f" (+{len(small_fonts) - 1} more)" if len(small_fonts) > 1 else ""
                ),
            })
        else:
            checks.append({
                "id": "F4", "category": "Mobile", "title": "Font Size",
                "status": "pass",
                "detail": "No inline font-size < 12px detected",
            })

        # ── F5: Content width ────────────────────────────────────
        wide_elements: list[str] = []
        for tag in soup.find_all(style=True):
            style = tag.get("style", "")
            # Check for width > 100vw
            vw_match = re.search(r"width\s*:\s*(\d+)vw", style)
            if vw_match and int(vw_match.group(1)) > 100:
                wide_elements.append(f"<{tag.name}> width: {vw_match.group(1)}vw")
            # Check for fixed px width > 400
            px_match = re.search(r"width\s*:\s*(\d+)px", style)
            if px_match and int(px_match.group(1)) > 400:
                wide_elements.append(f"<{tag.name}> width: {px_match.group(1)}px")

        if wide_elements:
            checks.append({
                "id": "F5", "category": "Mobile", "title": "Content Width",
                "status": "warn",
                "detail": f"{len(wide_elements)} element(s) may exceed viewport: {wide_elements[0]}" + (
                    f" (+{len(wide_elements) - 1} more)" if len(wide_elements) > 1 else ""
                ),
            })
        else:
            checks.append({
                "id": "F5", "category": "Mobile", "title": "Content Width",
                "status": "pass",
                "detail": "No inline styles with width > 100vw or > 400px detected",
            })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }
