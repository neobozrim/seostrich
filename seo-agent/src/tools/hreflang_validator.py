from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


_VALID_LANG_CODES = {
    "en", "bg", "de", "fr", "es", "it", "pt", "ru", "zh", "ja", "ko", "ar",
    "hi", "tr", "pl", "nl", "sv", "da", "no", "fi", "cs", "el", "hu", "ro",
    "uk", "hr", "sk", "sl", "lt", "lv", "et", "he", "th", "vi", "id", "ms",
}

_VALID_REGION_CODES = {
    "us", "gb", "au", "ca", "nz", "ie", "za", "in", "de", "fr", "es", "it",
    "pt", "br", "mx", "ar", "cl", "co", "ru", "cn", "jp", "kr", "tr", "pl",
    "nl", "be", "ch", "at", "se", "dk", "no", "fi", "cz", "gr", "hu", "ro",
    "bg", "ua", "hr", "sk", "si", "lt", "lv", "ee", "il", "th", "vn", "id",
    "my", "sg", "ph", "tw", "hk", "sa", "ae", "eg", "ng", "ke", "gh",
}

_LANG_REGION_RE = re.compile(r"^([a-z]{2})(?:-([A-Za-z]{2}))?$")


def _parse_hreflang(value: str) -> tuple[str, str | None] | None:
    """Parse hreflang value into (lang, region_or_none). Returns None if invalid."""
    if value == "x-default":
        return ("x-default", None)
    m = _LANG_REGION_RE.match(value)
    if not m:
        return None
    lang = m.group(1).lower()
    region = m.group(2).lower() if m.group(2) else None
    return (lang, region)


def hreflang_validator(urls: list[str]) -> dict:
    """Validate hreflang implementation across a set of URLs."""
    if not urls:
        return {
            "urls_checked": 0,
            "valid_pairs": 0,
            "missing_return_links": [],
            "invalid_codes": [],
            "unqualified_urls": [],
            "has_x_default": False,
            "methods_detected": [],
            "issues": [],
        }

    normalized: list[str] = []
    for u in urls:
        if not u.startswith("http"):
            u = f"https://{u}"
        normalized.append(u)

    issues: list[str] = []
    missing_return_links: list[dict] = []
    invalid_codes: list[dict] = []
    unqualified_urls: list[str] = []
    methods_detected: set[str] = set()
    has_x_default = False
    valid_pairs = 0

    # Mapping: (source_url, lang) -> target_url
    hreflang_map: dict[tuple[str, str], str] = {}

    with httpx.Client(
        timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
    ) as client:
        for url in normalized:
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
            except Exception:
                continue

            # Check HTTP header-based hreflang (Link header)
            link_header = resp.headers.get("link", "")
            if "hreflang" in link_header.lower():
                methods_detected.add("http_header")
                # Parse Link headers
                for part in link_header.split(","):
                    part = part.strip()
                    hm = re.search(r'hreflang=["\']?([^"\'>\s;]+)', part, re.I)
                    lm = re.search(r'<([^>]+)>', part)
                    if hm and lm:
                        hl_value = hm.group(1).lower()
                        target = lm.group(1)
                        hreflang_map[(url, hl_value)] = target
                        if hl_value == "x-default":
                            has_x_default = True

            # Check HTML hreflang
            soup = BeautifulSoup(resp.text[:200_000], "html.parser")
            html_links = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
            if html_links:
                methods_detected.add("html")

            for link_tag in html_links:
                hl_value = (link_tag.get("hreflang") or "").strip().lower()
                href = (link_tag.get("href") or "").strip()

                if not hl_value or not href:
                    continue

                # x-default check
                if hl_value == "x-default":
                    has_x_default = True

                # Validate language/region codes
                parsed = _parse_hreflang(hl_value)
                if parsed is None:
                    invalid_codes.append({"url": url, "code": hl_value})
                    issues.append(f"Invalid hreflang code '{hl_value}' on {url}")
                    continue

                lang, region = parsed
                if lang != "x-default" and lang not in _VALID_LANG_CODES:
                    invalid_codes.append({"url": url, "code": hl_value})
                    issues.append(f"Unknown language code '{lang}' in hreflang '{hl_value}' on {url}")

                if region and region not in _VALID_REGION_CODES:
                    invalid_codes.append({"url": url, "code": hl_value})
                    issues.append(f"Unknown region code '{region}' in hreflang '{hl_value}' on {url}")

                # URL qualification
                if not href.startswith("http"):
                    unqualified_urls.append(href)
                    issues.append(f"Unqualified hreflang URL on {url}: {href}")

                hreflang_map[(url, hl_value)] = href

    # Validate bidirectional links
    for (source_url, lang), target_url in hreflang_map.items():
        if lang == "x-default":
            # x-default doesn't require return link
            continue
        # The target URL should have a hreflang back to source_url
        # Find the lang that source_url is tagged as from target_url's perspective
        # We need to find: target_url has hreflang (some_lang) -> source_url
        # And source_url has hreflang (lang) -> target_url (already true)

        # Check if target_url has any hreflang pointing back to source_url
        found_return = False
        for (t_url, t_lang), t_target in hreflang_map.items():
            if t_url == target_url and t_target == source_url:
                found_return = True
                break
            # Also check normalized
            if t_url.rstrip("/") == target_url.rstrip("/") and t_target.rstrip("/") == source_url.rstrip("/"):
                found_return = True
                break

        if found_return:
            valid_pairs += 1
        else:
            missing_return_links.append({
                "from_url": source_url,
                "to_url": target_url,
                "lang": lang,
            })
            issues.append(
                f"Missing return hreflang: {target_url} does not link back to {source_url} for lang '{lang}'"
            )

    # Detect conflicting methods
    if "html" in methods_detected and "http_header" in methods_detected:
        issues.append(
            "Both HTML hreflang and HTTP header hreflang detected. "
            "Use one method consistently to avoid conflicts."
        )

    if not has_x_default and len(normalized) > 1:
        issues.append("No x-default hreflang found. Consider adding one for fallback.")

    return {
        "urls_checked": len(normalized),
        "valid_pairs": valid_pairs,
        "missing_return_links": missing_return_links,
        "invalid_codes": invalid_codes,
        "unqualified_urls": unqualified_urls,
        "has_x_default": has_x_default,
        "methods_detected": sorted(methods_detected),
        "issues": issues,
    }
