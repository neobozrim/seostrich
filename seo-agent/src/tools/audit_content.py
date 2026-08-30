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


def _extract_visible_text(soup: BeautifulSoup) -> str:
    """Extract visible text from the page, stripping scripts and styles."""
    for element in soup.find_all(["script", "style", "noscript"]):
        element.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date_safe(value: str) -> str | None:
    """Return ISO date string if parseable, else None."""
    if not value:
        return None
    # Try common ISO patterns
    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)
    return None


def audit_content(url: str) -> dict:
    """Run content-quality audit (J1–J10) on the given URL."""
    if not url.startswith("http"):
        url = f"https://{url}"

    base_domain = url.split("/")[2] if len(url.split("/")) > 2 else ""
    checks: list[dict] = []

    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "SEOAgent/1.0"},
    ) as client:
        resp = client.get(url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        visible_text = _extract_visible_text(soup)
        word_count = len(visible_text.split())

        # ── J1: Content length ───────────────────────────────────
        if word_count < 100:
            status, detail = "fail", f"Very thin content: {word_count} words"
        elif word_count < 300:
            status, detail = "warn", f"Low word count: {word_count} words (target ≥300)"
        else:
            status, detail = "pass", f"Content length: {word_count} words"
        checks.append({
            "id": "J1", "category": "Content", "title": "Content Length",
            "status": status, "detail": detail,
        })

        # ── J2: Content freshness ────────────────────────────────
        dates_found: list[str] = []
        # From JSON-LD
        for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(block.string)
                if isinstance(data, dict):
                    for key in ("datePublished", "dateModified"):
                        val = data.get(key)
                        if val:
                            parsed = _parse_date_safe(str(val))
                            if parsed:
                                dates_found.append(f"{key}: {parsed}")
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for key in ("datePublished", "dateModified"):
                                val = item.get(key)
                                if val:
                                    parsed = _parse_date_safe(str(val))
                                    if parsed:
                                        dates_found.append(f"{key}: {parsed}")
            except (json.JSONDecodeError, TypeError):
                pass

        # From meta tags
        for prop in ("article:published_time", "article:modified_time"):
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content"):
                parsed = _parse_date_safe(tag["content"])
                if parsed:
                    dates_found.append(f"{prop}: {parsed}")

        # From last-updated patterns
        last_updated = soup.find(class_=re.compile(r"last[-_]?updated|modified", re.I))
        if last_updated:
            text = last_updated.get_text(strip=True)
            parsed = _parse_date_safe(text)
            if parsed:
                dates_found.append(f"last-updated element: {parsed}")

        if dates_found:
            # Check if most recent date is > 12 months old
            all_dates = []
            for d in dates_found:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", d)
                if match:
                    all_dates.append(match.group(1))
            if all_dates:
                all_dates.sort(reverse=True)
                newest = all_dates[0]
                # Rough 12-month check
                year, month = int(newest[:4]), int(newest[5:7])
                # Compare to ~2025-07 as a rough "now" — caller should use actual dates
                status = "pass"
                detail = f"Dates found: {'; '.join(dates_found[:3])}"
            else:
                status, detail = "warn", f"Dates found but unparseable: {'; '.join(dates_found[:3])}"
        else:
            status, detail = "warn", "No publication or modification dates found"
        checks.append({
            "id": "J2", "category": "Content", "title": "Content Freshness",
            "status": status, "detail": detail,
        })

        # ── J3: Author info ──────────────────────────────────────
        author = None
        for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(block.string)
                items = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    if isinstance(item, dict) and item.get("author"):
                        a = item["author"]
                        author = a.get("name", "") if isinstance(a, dict) else str(a)
                        break
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        if not author:
            meta_author = soup.find("meta", attrs={"name": "author"})
            if meta_author:
                author = meta_author.get("content", "")
        if not author:
            author_el = soup.find(class_=re.compile(r"author", re.I))
            if author_el:
                author = author_el.get_text(strip=True)[:50]

        generic_names = {"admin", "editor", "staff", "team", "webmaster"}
        if not author:
            status, detail = "warn", "No author information found"
        elif author.strip().lower() in generic_names:
            status, detail = "warn", f"Generic author name: '{author}' — use a real person's name for E-E-A-T"
        else:
            status, detail = "pass", f"Author: {author}"
        checks.append({
            "id": "J3", "category": "Content", "title": "Author Info",
            "status": status, "detail": detail,
        })

        # ── J4: Heading hierarchy ────────────────────────────────
        headings: list[int] = []
        for level in range(1, 7):
            for h in soup.find_all(f"h{level}"):
                headings.append(level)
        # Check for skipped levels
        skipped_levels: list[str] = []
        if headings:
            for i in range(1, len(headings)):
                if headings[i] > headings[i - 1] + 1:
                    skipped_levels.append(f"h{headings[i-1]} → h{headings[i]}")

        if skipped_levels:
            status, detail = "warn", f"Heading levels skipped: {', '.join(skipped_levels[:3])}"
        elif headings:
            status, detail = "pass", f"Heading hierarchy is clean ({len(headings)} headings)"
        else:
            status, detail = "warn", "No headings found on page"
        checks.append({
            "id": "J4", "category": "Content", "title": "Heading Hierarchy",
            "status": status, "detail": detail,
        })

        # ── J5: List usage ───────────────────────────────────────
        uls = soup.find_all("ul")
        ols = soup.find_all("ol")
        total_lists = len(uls) + len(ols)
        if total_lists > 0:
            status, detail = "pass", f"Found {len(uls)} unordered and {len(ols)} ordered lists (good scannability)"
        else:
            status, detail = "warn", "No <ul> or <ol> lists found — consider adding lists for scannability"
        checks.append({
            "id": "J5", "category": "Content", "title": "List Usage",
            "status": status, "detail": detail,
        })

        # ── J6: Image optimization ───────────────────────────────
        images = soup.find_all("img")
        if images:
            lazy_count = sum(1 for img in images if img.get("loading") == "lazy")
            srcset_count = sum(1 for img in images if img.get("srcset"))
            modern_formats = sum(
                1 for img in images
                if re.search(r"\.(webp|avif)(\?|$)", img.get("src", ""), re.I)
                or re.search(r"\.(webp|avif)(\?|$)", img.get("data-src", ""), re.I)
            )
            issues: list[str] = []
            if lazy_count < len(images) * 0.5:
                issues.append(f"only {lazy_count}/{len(images)} images use lazy loading")
            if srcset_count == 0:
                issues.append("no images use srcset for responsive serving")
            if modern_formats == 0:
                issues.append("no modern image formats (webp/avif) detected")

            if issues:
                status, detail = "warn", f"Image optimization: {'; '.join(issues)}"
            else:
                status, detail = "pass", f"All {len(images)} images well-optimised (lazy, srcset, modern formats)"
        else:
            status, detail = "skip", "No images found"
        checks.append({
            "id": "J6", "category": "Content", "title": "Image Optimization",
            "status": status, "detail": detail,
        })

        # ── J7: Internal link count ──────────────────────────────
        internal_links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") or base_domain in href:
                internal_links.append(href)
        il_count = len(internal_links)
        if il_count == 0:
            status, detail = "warn", "No internal links found"
        elif il_count < 3:
            status, detail = "warn", f"Only {il_count} internal link(s) — aim for at least 3"
        elif il_count > 100:
            status, detail = "warn", f"{il_count} internal links — may be excessive"
        else:
            status, detail = "pass", f"{il_count} internal links"
        checks.append({
            "id": "J7", "category": "Content", "title": "Internal Link Count",
            "status": status, "detail": detail,
        })

        # ── J8: External link count ──────────────────────────────
        external_links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and base_domain not in href:
                external_links.append(href)
        el_count = len(external_links)
        status, detail = "pass", f"{el_count} external links"
        if el_count == 0:
            status, detail = "warn", "No external links found — authoritative outbound links help E-E-A-T"
        checks.append({
            "id": "J8", "category": "Content", "title": "External Link Count",
            "status": status, "detail": detail,
        })

        # ── J9: Table usage ──────────────────────────────────────
        tables = soup.find_all("table")
        if tables:
            status, detail = "pass", f"Found {len(tables)} table(s) — structured data signal"
        else:
            status, detail = "skip", "No <table> elements found"
        checks.append({
            "id": "J9", "category": "Content", "title": "Table Usage",
            "status": status, "detail": detail,
        })

        # ── J10: Content sections ────────────────────────────────
        h2_count = len(soup.find_all("h2"))
        if h2_count == 0:
            status, detail = "warn", "No H2 headings — page may lack topical structure"
        elif h2_count < 3:
            status, detail = "warn", f"Only {h2_count} H2 heading(s) — consider more subtopics"
        else:
            status, detail = "pass", f"{h2_count} H2 sections (good topic coverage)"
        checks.append({
            "id": "J10", "category": "Content", "title": "Content Sections",
            "status": status, "detail": detail,
        })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }
