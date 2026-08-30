from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup


# Common date patterns for fallback parsing
_DATE_PATTERNS = [
    re.compile(r"Updated\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})", re.I),
    re.compile(r"Last\s+(?:modified|updated)\s+(\w+\s+\d{1,2},?\s+\d{4})", re.I),
    re.compile(r"Published\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", re.I),
    re.compile(r"(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:?\d{2}|Z)?)?)"),
    re.compile(r"(\d{1,2}/\d{1,2}/\d{4})"),
    re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})"),
]

_COMMON_FORMATS = [
    "%B %d, %Y",       # January 15, 2024
    "%B %d %Y",        # January 15 2024
    "%b %d, %Y",       # Jan 15, 2024
    "%b %d %Y",        # Jan 15 2024
    "%d %B %Y",        # 15 January 2024
    "%d %b %Y",        # 15 Jan 2024
    "%m/%d/%Y",        # 01/15/2024
    "%d.%m.%Y",        # 15.01.2024
]


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse a date string into a datetime object."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # Try ISO 8601 first
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # Try common formats
    for fmt in _COMMON_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _extract_dates(html: str) -> dict[str, datetime | None]:
    """Extract date signals from HTML and return the best dates found."""
    soup = BeautifulSoup(html[:200_000], "html.parser")
    found: dict[str, datetime | None] = {
        "published": None,
        "modified": None,
    }

    # 1. JSON-LD structured data
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                for item in data:
                    _check_jsonld_dates(item, found)
            elif isinstance(data, dict):
                _check_jsonld_dates(data, found)
        except (json.JSONDecodeError, TypeError):
            continue

    # 2. Meta tags (Open Graph / article)
    meta_published = soup.find("meta", attrs={"property": "article:published_time"})
    if meta_published and not found["published"]:
        found["published"] = _parse_date(meta_published.get("content", ""))

    meta_modified = soup.find("meta", attrs={"property": "article:modified_time"})
    if meta_modified:
        found["modified"] = _parse_date(meta_modified.get("content", ""))

    meta_date = soup.find("meta", attrs={"name": "date"})
    if meta_date and not found["published"]:
        found["published"] = _parse_date(meta_date.get("content", ""))

    # 3. <time> elements with datetime attribute
    for time_el in soup.find_all("time", attrs={"datetime": True}):
        dt = _parse_date(time_el["datetime"])
        if dt:
            # Heuristic: check parent/attributes for published vs modified
            classes = " ".join(time_el.get("class", [])).lower()
            parent_classes = ""
            if time_el.parent:
                parent_classes = " ".join(time_el.parent.get("class", [])).lower()
            context = classes + " " + parent_classes

            if "modif" in context or "updated" in context:
                if not found["modified"]:
                    found["modified"] = dt
            elif not found["published"]:
                found["published"] = dt

    # 4. Text pattern fallback
    text = soup.get_text(" ", strip=True)[:10_000]
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            dt = _parse_date(match.group(1))
            if dt and not found["published"]:
                found["published"] = dt
                break

    return found


def _check_jsonld_dates(data: dict, found: dict) -> None:
    """Extract dates from a JSON-LD object."""
    if not isinstance(data, dict):
        return
    for key in ("datePublished", "dateCreated"):
        if key in data and not found["published"]:
            found["published"] = _parse_date(str(data[key]))
    if "dateModified" in data:
        dt = _parse_date(str(data["dateModified"]))
        if dt:
            found["modified"] = dt


def content_freshness_scan(
    urls: list[str], stale_threshold_months: int = 6
) -> dict:
    """Scan URLs for content freshness based on date signals."""
    if not urls:
        return {
            "urls_scanned": 0,
            "fresh_pages": [],
            "stale_pages": [],
            "pages_without_dates": [],
            "avg_content_age_days": 0,
            "stale_pct": "0%",
            "recommendations": [],
        }

    normalized: list[str] = []
    for u in urls:
        if not u.startswith("http"):
            u = f"https://{u}"
        normalized.append(u)

    fresh_pages: list[dict] = []
    stale_pages: list[dict] = []
    pages_without_dates: list[str] = []
    recommendations: list[str] = []

    now = datetime.now(timezone.utc)
    threshold_days = stale_threshold_months * 30
    ages: list[int] = []

    with httpx.Client(
        timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
    ) as client:
        for url in normalized:
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    pages_without_dates.append(url)
                    continue
            except Exception:
                pages_without_dates.append(url)
                continue

            dates = _extract_dates(resp.text)
            # Use modified date if available, else published
            best_date = dates["modified"] or dates["published"]

            if best_date is None:
                pages_without_dates.append(url)
                continue

            age_days = (now - best_date).days
            ages.append(age_days)

            date_info = {
                "url": url,
                "age_days": age_days,
                "published": dates["published"].isoformat() if dates["published"] else None,
                "modified": dates["modified"].isoformat() if dates["modified"] else None,
            }

            if age_days <= threshold_days:
                fresh_pages.append(date_info)
            else:
                stale_pages.append(date_info)

    # Summary
    total_scanned = len(normalized)
    stale_pct = "0%"
    if total_scanned > 0:
        stale_pct = f"{len(stale_pages) / total_scanned * 100:.0f}%"

    avg_age = 0
    if ages:
        avg_age = round(sum(ages) / len(ages))

    # Recommendations
    if stale_pages:
        recommendations.append(
            f"{len(stale_pages)} pages are older than {stale_threshold_months} months. "
            "Review and update with current information, new data, and fresh examples."
        )
    if pages_without_dates:
        recommendations.append(
            f"{len(pages_without_dates)} pages have no date signals. "
            "Add datePublished and dateModified to JSON-LD and article meta tags."
        )
    if ages and avg_age > threshold_days:
        recommendations.append(
            f"Average content age is {avg_age} days. "
            "Consider a content refresh schedule to keep pages up-to-date."
        )

    return {
        "urls_scanned": total_scanned,
        "fresh_pages": fresh_pages,
        "stale_pages": stale_pages,
        "pages_without_dates": pages_without_dates,
        "avg_content_age_days": avg_age,
        "stale_pct": stale_pct,
        "recommendations": recommendations,
    }
