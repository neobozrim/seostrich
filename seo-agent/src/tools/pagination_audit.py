from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


_PAGINATION_QUERY_PATTERNS = [
    re.compile(r"[?&]page=\d+", re.I),
    re.compile(r"[?&]p=\d+", re.I),
    re.compile(r"[?&]pg=\d+", re.I),
    re.compile(r"[?&]offset=\d+", re.I),
]

_PAGINATION_PATH_PATTERNS = [
    re.compile(r"/page/\d+", re.I),
    re.compile(r"/p/\d+", re.I),
]

_FRAGMENT_PAGINATION = re.compile(r"#page=\d+", re.I)

_LOAD_MORE_PATTERNS = [
    re.compile(r"load\s+more", re.I),
    re.compile(r"show\s+more", re.I),
    re.compile(r"view\s+more", re.I),
]

_INFINITE_SCROLL_SIGNALS = [
    re.compile(r"infinite[_-]?scroll", re.I),
    re.compile(r"IntersectionObserver", re.I),
    re.compile(r"onscroll.*load", re.I),
]


def pagination_audit(url: str) -> dict:
    """Analyze pagination implementation on a given URL."""
    if not url.startswith("http"):
        url = f"https://{url}"

    issues: list[str] = []
    recommendations: list[str] = []
    is_paginated = False
    method = "none"
    total_pages_detected: int | None = None
    unique_urls = True
    crawlable = True
    canonical_correct: bool | None = None
    uses_deprecated_rel = False

    try:
        with httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                issues.append(f"Page returned status {resp.status_code}")
                return {
                    "url": url,
                    "is_paginated": False,
                    "method": "none",
                    "total_pages_detected": None,
                    "unique_urls": True,
                    "crawlable": True,
                    "canonical_correct": None,
                    "uses_deprecated_rel": False,
                    "issues": issues,
                    "recommendations": recommendations,
                }
            html = resp.text[:300_000]
    except Exception as exc:
        return {
            "url": url,
            "is_paginated": False,
            "method": "none",
            "total_pages_detected": None,
            "unique_urls": True,
            "crawlable": True,
            "canonical_correct": None,
            "uses_deprecated_rel": False,
            "issues": [f"Failed to fetch page: {exc}"],
            "recommendations": [],
        }

    soup = BeautifulSoup(html, "html.parser")

    # --- Detect rel="next" / rel="prev" ---
    rel_next = soup.find("link", attrs={"rel": re.compile(r"next", re.I)})
    rel_prev = soup.find("link", attrs={"rel": re.compile(r"prev", re.I)})

    if rel_next or rel_prev:
        uses_deprecated_rel = True
        is_paginated = True
        method = "links"
        issues.append(
            "rel=\"next\"/\"prev\" tags found. Google deprecated these in 2019 — "
            "they are ignored by Google but may still be used by Bing and others."
        )
        recommendations.append(
            "rel=\"next\"/\"prev\" is deprecated by Google. "
            "It's safe to keep for Bing but don't rely on it for Google indexing."
        )

    # --- Detect <a href> pagination links ---
    pagination_links: list[str] = []
    fragment_links = False

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        anchor_text = a_tag.get_text(strip=True)

        # Check for fragment-based pagination
        if _FRAGMENT_PAGINATION.search(href):
            fragment_links = True
            is_paginated = True

        # Check for query-param pagination
        for pat in _PAGINATION_QUERY_PATTERNS:
            if pat.search(href):
                pagination_links.append(href)
                is_paginated = True
                break

        # Check for path-based pagination
        for pat in _PAGINATION_PATH_PATTERNS:
            if pat.search(href):
                pagination_links.append(href)
                is_paginated = True
                break

        # Check for numbered links (common in pagination)
        if re.match(r"^\d+$", anchor_text) and href != url:
            # Check if the href is a variant of current URL
            parsed_href = urlparse(href)
            parsed_current = urlparse(url)
            if parsed_href.netloc == parsed_current.netloc:
                if not any(pat.search(href) for pat in _PAGINATION_QUERY_PATTERNS + _PAGINATION_PATH_PATTERNS):
                    pagination_links.append(href)
                    is_paginated = True

    if pagination_links and method == "none":
        method = "links"

    # Fragment-based pagination is a problem
    if fragment_links:
        unique_urls = False
        crawlable = False
        issues.append(
            "Fragment-based pagination (#page=2) detected. "
            "Google cannot crawl fragment-based URLs — each page must have a unique URL."
        )
        recommendations.append(
            "Replace fragment-based pagination with unique URLs using query parameters "
            "(?page=2) or path segments (/page/2/)."
        )

    # --- Detect load more button ---
    load_more_found = False
    for pattern in _LOAD_MORE_PATTERNS:
        buttons = soup.find_all(
            ["button", "a", "div", "span"],
            string=pattern,
        )
        if buttons:
            load_more_found = True
            break
        # Also check data attributes and class names
        for el in soup.find_all(attrs={"class": re.compile(r"load[_-]?more", re.I)}):
            load_more_found = True
            break
        for el in soup.find_all(attrs={"data-action": re.compile(r"load[_-]?more", re.I)}):
            load_more_found = True
            break

    if load_more_found:
        is_paginated = True
        if method == "none":
            method = "load_more"
        # Check if load more generates unique URLs
        load_more_el = soup.find_all(
            attrs={"class": re.compile(r"load[_-]?more", re.I)}
        )
        has_unique_url = False
        for el in load_more_el:
            if el.name == "a" and el.get("href"):
                href = el["href"]
                if href and href != "#" and not href.startswith("javascript:"):
                    has_unique_url = True

        if not has_unique_url:
            unique_urls = False
            crawlable = False
            issues.append(
                "Load more button detected without unique URLs. "
                "Google cannot discover content behind non-link buttons."
            )
            recommendations.append(
                "Ensure load more functionality generates unique, crawlable URLs for each page "
                "and implement progressive enhancement with <a href> fallback."
            )

    # --- Detect infinite scroll ---
    for signal in _INFINITE_SCROLL_SIGNALS:
        if signal.search(html):
            is_paginated = True
            if method == "none":
                method = "infinite_scroll"
            unique_urls = False
            crawlable = False
            issues.append(
                "Infinite scroll detected without unique URLs. "
                "Google cannot crawl infinite scroll implementations without unique page URLs."
            )
            recommendations.append(
                "Implement infinite scroll with unique URLs for each loaded page. "
                "Use pushState to update the URL as content loads, and provide <a href> "
                "fallback links for crawlers."
            )
            break

    # --- Estimate total pages ---
    if pagination_links:
        # Look for the highest page number in pagination links
        max_page = 1
        for link in pagination_links:
            for pat in _PAGINATION_QUERY_PATTERNS + _PAGINATION_PATH_PATTERNS:
                m = pat.search(link)
                if m:
                    num_match = re.search(r"\d+", m.group())
                    if num_match:
                        max_page = max(max_page, int(num_match.group()))
            # Also check numbered anchor text
        if max_page > 1:
            total_pages_detected = max_page

    # --- Check canonical ---
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag:
        canonical_href = canonical_tag.get("href", "")
        parsed_canonical = urlparse(canonical_href)
        parsed_current = urlparse(url)
        # Self-referencing canonical check
        if parsed_canonical.path == parsed_current.path:
            canonical_correct = True
        else:
            canonical_correct = False
            issues.append(
                f"Canonical URL ({canonical_href}) does not match current page URL. "
                "Each paginated page should have a self-referencing canonical."
            )
            recommendations.append(
                "Set each paginated page's canonical to point to itself, not to page 1."
            )

    # --- Crawlable check for <a href> pagination ---
    if is_paginated and method == "links" and not fragment_links:
        # Verify pagination links use <a href> (crawlable)
        non_a_pagination = 0
        for el in soup.find_all(
            attrs={"class": re.compile(r"paginat|page[_-]?num|pager", re.I)}
        ):
            if el.name not in ("a",) and not el.find("a"):
                non_a_pagination += 1
        if non_a_pagination > 0:
            crawlable = False
            issues.append(
                f"{non_a_pagination} pagination elements are not <a href> links and may not be crawlable."
            )

    return {
        "url": url,
        "is_paginated": is_paginated,
        "method": method,
        "total_pages_detected": total_pages_detected,
        "unique_urls": unique_urls,
        "crawlable": crawlable,
        "canonical_correct": canonical_correct,
        "uses_deprecated_rel": uses_deprecated_rel,
        "issues": issues,
        "recommendations": recommendations,
    }
