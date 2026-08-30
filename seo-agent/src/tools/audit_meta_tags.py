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


def audit_meta_tags(url: str) -> dict:
    """Run meta-tags audit (B1–B10) on the given URL."""
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
        final_url = str(resp.url)

        # ── B1: Title tag (30-60 chars) ───────────────────────────
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        title_len = len(title)
        if not title:
            status, detail = "fail", "No title tag found"
        elif 30 <= title_len <= 60:
            status, detail = "pass", f"Title: {title} ({title_len} chars)"
        else:
            status, detail = "warn", f"Title length {title_len} chars (target 30-60): {title}"
        checks.append({
            "id": "B1", "category": "Meta Tags", "title": "Title Tag",
            "status": status, "detail": detail,
        })

        # ── B2: Meta description (110-160 chars) ──────────────────
        meta_desc = soup.find("meta", attrs={"name": "description"})
        desc_text = meta_desc.get("content", "").strip() if meta_desc else ""
        desc_len = len(desc_text)
        if not desc_text:
            status, detail = "fail", "No meta description found"
        elif 110 <= desc_len <= 160:
            status, detail = "pass", f"Meta description: {desc_len} chars"
        else:
            status, detail = "warn", f"Meta description length {desc_len} chars (target 110-160)"
        checks.append({
            "id": "B2", "category": "Meta Tags", "title": "Meta Description",
            "status": status, "detail": detail,
        })

        # ── B3: H1 tag (exactly 1) ───────────────────────────────
        h1s = soup.find_all("h1")
        h1_count = len(h1s)
        if h1_count == 1:
            status, detail = "pass", f"H1: {h1s[0].get_text(strip=True)[:80]}"
        elif h1_count == 0:
            status, detail = "fail", "No H1 tag found"
        else:
            status, detail = "warn", f"Found {h1_count} H1 tags (should be exactly 1)"
        checks.append({
            "id": "B3", "category": "Meta Tags", "title": "H1 Tag",
            "status": status, "detail": detail,
        })

        # ── B4: Duplicate title/description ───────────────────────
        if title and desc_text:
            title_normalized = title.lower().strip()
            desc_normalized = desc_text.lower().strip()
            if title_normalized == desc_normalized:
                status, detail = "warn", "Title and meta description are identical — Google may pick wrong snippet"
            else:
                status, detail = "pass", "Title and meta description are distinct"
        else:
            status, detail = "skip", "Cannot compare — title or description missing"
        checks.append({
            "id": "B4", "category": "Meta Tags", "title": "Duplicate Title/Desc",
            "status": status, "detail": detail,
        })

        # ── B5: Open Graph tags ───────────────────────────────────
        og_required = ["og:title", "og:description", "og:image", "og:type", "og:url"]
        og_present: list[str] = []
        og_missing: list[str] = []
        og_image_valid = True
        for prop in og_required:
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content", "").strip():
                og_present.append(prop)
                if prop == "og:image":
                    img_url = tag["content"].strip()
                    if not img_url.startswith("http"):
                        og_image_valid = False
            else:
                og_missing.append(prop)

        detail_parts = []
        if og_present:
            detail_parts.append(f"Present: {', '.join(og_present)}")
        if og_missing:
            detail_parts.append(f"Missing: {', '.join(og_missing)}")
        if not og_image_valid:
            detail_parts.append("og:image is not an absolute URL")

        if not og_missing and og_image_valid:
            status = "pass"
        elif og_missing and len(og_missing) <= 2:
            status = "warn"
        else:
            status = "fail" if og_missing else "warn"
        checks.append({
            "id": "B5", "category": "Meta Tags", "title": "Open Graph Tags",
            "status": status, "detail": "; ".join(detail_parts) or "No OG tags found",
        })

        # ── B6: Twitter Card tags ─────────────────────────────────
        tw_required = ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]
        tw_present: list[str] = []
        tw_missing: list[str] = []
        for prop in tw_required:
            tag = soup.find("meta", attrs={"name": prop}) or soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content", "").strip():
                tw_present.append(prop)
            else:
                tw_missing.append(prop)

        detail_parts = []
        if tw_present:
            detail_parts.append(f"Present: {', '.join(tw_present)}")
        if tw_missing:
            detail_parts.append(f"Missing: {', '.join(tw_missing)}")

        if not tw_missing:
            status = "pass"
        elif tw_missing and len(tw_missing) <= 2:
            status = "warn"
        else:
            status = "fail"
        checks.append({
            "id": "B6", "category": "Meta Tags", "title": "Twitter Card Tags",
            "status": status, "detail": "; ".join(detail_parts) or "No Twitter Card tags found",
        })

        # ── B7: Canonical consistency ─────────────────────────────
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical_tag.get("href", "").strip() if canonical_tag else ""
        og_url_tag = soup.find("meta", attrs={"property": "og:url"})
        og_url = og_url_tag.get("content", "").strip() if og_url_tag else ""

        issues: list[str] = []
        if canonical_href and not canonical_href.startswith("http"):
            issues.append("canonical is relative URL")
        if canonical_href and canonical_href.rstrip("/") != final_url.rstrip("/"):
            issues.append(f"canonical ({canonical_href}) differs from final URL ({final_url})")
        if og_url and canonical_href and og_url.rstrip("/") != canonical_href.rstrip("/"):
            issues.append(f"og:url ({og_url}) differs from canonical ({canonical_href})")

        if not canonical_href and not og_url:
            status, detail = "warn", "No canonical or og:url found"
        elif issues:
            status, detail = "warn", "; ".join(issues)
        else:
            status, detail = "pass", "Canonical, final URL, and og:url are consistent"
        checks.append({
            "id": "B7", "category": "Meta Tags", "title": "Canonical Consistency",
            "status": status, "detail": detail,
        })

        # ── B8: Viewport meta ─────────────────────────────────────
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if viewport and "width=device-width" in (viewport.get("content") or ""):
            status, detail = "pass", "Viewport meta tag correctly set"
        else:
            status, detail = "fail", "Missing or incorrect viewport meta tag"
        checks.append({
            "id": "B8", "category": "Meta Tags", "title": "Viewport",
            "status": status, "detail": detail,
        })

        # ── B9: Charset declaration ──────────────────────────────
        charset_tag = soup.find("meta", attrs={"charset": True})
        if charset_tag:
            charset_val = charset_tag.get("charset", "").lower().strip()
            if charset_val == "utf-8":
                status, detail = "pass", f"Charset declared: {charset_val}"
            else:
                status, detail = "warn", f"Charset declared as '{charset_val}' — utf-8 recommended"
        else:
            # Also check http-equiv Content-Type
            ct = soup.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
            if ct and "utf-8" in (ct.get("content") or "").lower():
                status, detail = "pass", "Charset utf-8 declared via http-equiv"
            else:
                status, detail = "warn", "No charset declaration found"
        checks.append({
            "id": "B9", "category": "Meta Tags", "title": "Charset Declaration",
            "status": status, "detail": detail,
        })

        # ── B10: Language declaration ─────────────────────────────
        html_tag = soup.find("html")
        lang_attr = html_tag.get("lang", "").strip() if html_tag else ""
        if lang_attr:
            status, detail = "pass", f"HTML lang='{lang_attr}'"
        else:
            status, detail = "warn", "No lang attribute on <html> tag"
        checks.append({
            "id": "B10", "category": "Meta Tags", "title": "Language Declaration",
            "status": status, "detail": detail,
        })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }
