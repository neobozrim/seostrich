from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx


_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
_VIDEO_NS = "http://www.google.com/schemas/sitemap-video/1.1"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"

_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2}|Z)?)?$"
)

_MAX_URLS = 50_000
_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def validate_sitemap(sitemap_url: str, site_url: str = "") -> dict:
    """Validate a sitemap XML file for correctness and best practices."""
    if not sitemap_url.startswith("http"):
        sitemap_url = f"https://{sitemap_url}"

    errors: list[str] = []
    warnings: list[str] = []
    urls: list[str] = []
    has_image_extension = False
    has_video_extension = False
    has_news_extension = False
    lastmod_present = 0
    lastmod_total = 0

    # Fetch
    try:
        with httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
        ) as client:
            resp = client.get(sitemap_url)
            resp.raise_for_status()
            raw = resp.content
    except Exception as exc:
        return {
            "sitemap_url": sitemap_url,
            "valid": False,
            "url_count": 0,
            "errors": [f"Failed to fetch sitemap: {exc}"],
            "warnings": [],
            "has_image_extension": False,
            "has_video_extension": False,
            "has_news_extension": False,
            "lastmod_coverage": "0%",
            "sample_urls": [],
        }

    # Size check
    content_length = len(raw)
    if content_length > _MAX_SIZE_BYTES:
        warnings.append(
            f"Sitemap exceeds 50 MB ({content_length / (1024*1024):.1f} MB). "
            "Split into smaller sitemaps."
        )

    # Parse XML
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return {
            "sitemap_url": sitemap_url,
            "valid": False,
            "url_count": 0,
            "errors": [f"XML parse error: {exc}"],
            "warnings": warnings,
            "has_image_extension": False,
            "has_video_extension": False,
            "has_news_extension": False,
            "lastmod_coverage": "0%",
            "sample_urls": [],
        }

    tag = root.tag
    # Strip namespace for comparison
    local_tag = tag.split("}")[-1] if "}" in tag else tag

    # Namespace check
    if "}" in tag:
        ns = tag.split("}")[0].lstrip("{")
        if ns != _SITEMAP_NS:
            errors.append(
                f"Unexpected namespace: {ns}. "
                f"Expected {_SITEMAP_NS}."
            )
    else:
        warnings.append("Sitemap has no namespace declaration.")

    # Handle sitemap index vs regular sitemap
    if local_tag == "sitemapindex":
        # Sitemap index — collect sub-sitemap URLs
        for sitemap_el in root:
            s_tag = sitemap_el.tag.split("}")[-1] if "}" in sitemap_el.tag else sitemap_el.tag
            if s_tag != "sitemap":
                continue
            loc_el = sitemap_el.find(f"{{{_SITEMAP_NS}}}loc")
            if loc_el is None:
                loc_el = sitemap_el.find("loc")
            if loc_el is None or not (loc_el.text or "").strip():
                errors.append("Sitemap index entry missing <loc>.")
                continue
            urls.append(loc_el.text.strip())
    elif local_tag == "urlset":
        # Regular sitemap
        seen: set[str] = set()
        for url_el in root:
            u_tag = url_el.tag.split("}")[-1] if "}" in url_el.tag else url_el.tag
            if u_tag != "url":
                continue

            # Check <loc>
            loc_el = url_el.find(f"{{{_SITEMAP_NS}}}loc")
            if loc_el is None:
                loc_el = url_el.find("loc")
            if loc_el is None:
                errors.append("URL entry missing <loc> element.")
                continue
            loc_text = (loc_el.text or "").strip()
            if not loc_text:
                errors.append("Empty <loc> element found.")
                continue

            # Duplicate check
            if loc_text in seen:
                errors.append(f"Duplicate URL: {loc_text}")
            seen.add(loc_text)
            urls.append(loc_text)

            # <lastmod> checks
            lastmod_el = url_el.find(f"{{{_SITEMAP_NS}}}lastmod")
            if lastmod_el is None:
                lastmod_el = url_el.find("lastmod")
            lastmod_total += 1
            if lastmod_el is not None and (lastmod_el.text or "").strip():
                lastmod_present += 1
                lm = lastmod_el.text.strip()
                if not _ISO8601_RE.match(lm):
                    warnings.append(f"Non-ISO 8601 lastmod for {loc_text}: {lm}")
                # Check if date is in the future
                date_part = lm[:10]
                try:
                    from datetime import date as _date

                    y, m, d = map(int, date_part.split("-"))
                    if _date(y, m, d) > _date.today():
                        warnings.append(f"Future lastmod for {loc_text}: {lm}")
                except (ValueError, IndexError):
                    pass

            # Extension namespaces
            if url_el.find(f"{{{_IMAGE_NS}}}image") is not None:
                has_image_extension = True
            if url_el.find(f"{{{_VIDEO_NS}}}video") is not None:
                has_video_extension = True
            if url_el.find(f"{{{_NEWS_NS}}}news") is not None:
                has_news_extension = True
    else:
        errors.append(f"Unexpected root element: <{local_tag}>. Expected <urlset> or <sitemapindex>.")

    # URL count warning
    url_count = len(urls)
    if url_count > _MAX_URLS:
        warnings.append(
            f"Sitemap contains {url_count:,} URLs (limit is {_MAX_URLS:,}). "
            "Split into multiple sitemaps."
        )

    # Domain verification
    if site_url:
        if not site_url.startswith("http"):
            site_url = f"https://{site_url}"
        site_domain = urlparse(site_url).netloc.lower()
        for u in urls:
            try:
                u_domain = urlparse(u).netloc.lower()
                if u_domain and u_domain != site_domain:
                    warnings.append(
                        f"URL does not belong to {site_domain}: {u}"
                    )
            except Exception:
                pass

    # lastmod coverage
    if lastmod_total > 0:
        coverage_pct = f"{lastmod_present / lastmod_total * 100:.0f}%"
    else:
        coverage_pct = "0%"

    valid = len(errors) == 0

    return {
        "sitemap_url": sitemap_url,
        "valid": valid,
        "url_count": url_count,
        "errors": errors,
        "warnings": warnings,
        "has_image_extension": has_image_extension,
        "has_video_extension": has_video_extension,
        "has_news_extension": has_news_extension,
        "lastmod_coverage": coverage_pct,
        "sample_urls": urls[:20],
    }
