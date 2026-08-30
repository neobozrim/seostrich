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


_ISO_639_1_CODES = {
    "en", "bg", "de", "fr", "es", "it", "pt", "ru", "zh", "ja", "ko",
    "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi", "cs", "el",
    "hu", "ro", "uk", "hr", "sk", "sl", "lt", "lv", "et",
    # Extended common codes
    "af", "am", "az", "be", "bn", "bs", "ca", "cy", "eo", "eu", "fa",
    "ga", "gl", "gu", "ha", "he", "hy", "id", "ig", "is", "ka", "kk",
    "km", "kn", "ku", "ky", "lb", "lo", "mk", "ml", "mn", "mr", "ms",
    "mt", "my", "ne", "or", "pa", "ps", "rw", "sd", "si", "so", "sq",
    "sr", "su", "sw", "ta", "te", "tg", "th", "tk", "tl", "ur", "uz",
    "vi", "xh", "yi", "yo", "zu",
}


def audit_i18n(url: str) -> dict:
    """Run internationalisation audit (I1–I6) on the given URL."""
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

        # Collect hreflang links
        hreflangs = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})

        # ── I1: hreflang tags ─────────────────────────────────────
        if hreflangs:
            has_x_default = any(h.get("hreflang") == "x-default" for h in hreflangs)
            if has_x_default:
                status, detail = "pass", f"Found {len(hreflangs)} hreflang tags with x-default"
            else:
                status, detail = "warn", f"Found {len(hreflangs)} hreflang tags (missing x-default)"
        else:
            lang_switchers = soup.find_all(class_=re.compile(r"lang|language|locale", re.I))
            if lang_switchers:
                status, detail = "warn", "Language switcher detected but no hreflang tags"
            else:
                status, detail = "skip", "No multilingual signals detected"
        checks.append({
            "id": "I1", "category": "i18n", "title": "Hreflang Tags",
            "status": status, "detail": detail,
        })

        # ── I2: hreflang bidirectional ───────────────────────────
        if hreflangs:
            hreflang_map: dict[str, str] = {}
            for h in hreflangs:
                lang = h.get("hreflang", "")
                href = h.get("href", "")
                if lang and href:
                    hreflang_map[lang] = href

            # Check up to 5 URLs for reciprocal links
            checked = 0
            missing_return: list[str] = []
            for lang, href in list(hreflang_map.items())[:5]:
                if lang == "x-default":
                    continue
                checked += 1
                try:
                    r = client.get(href)
                    if r.status_code == 200:
                        remote_soup = BeautifulSoup(r.text, "html.parser")
                        remote_hreflangs = remote_soup.find_all(
                            "link", attrs={"rel": "alternate", "hreflang": True},
                        )
                        # Check if any remote hreflang points back to original URL
                        found_return = False
                        for rh in remote_hreflangs:
                            rh_href = rh.get("href", "").rstrip("/")
                            if rh_href == url.rstrip("/"):
                                found_return = True
                                break
                        if not found_return:
                            missing_return.append(f"{lang} ({href})")
                except Exception:
                    missing_return.append(f"{lang} ({href}) — fetch failed")

            if missing_return:
                checks.append({
                    "id": "I2", "category": "i18n", "title": "Hreflang Bidirectional",
                    "status": "warn",
                    "detail": f"{len(missing_return)}/{checked} hreflang URLs missing return link: {', '.join(missing_return[:3])}",
                })
            else:
                checks.append({
                    "id": "I2", "category": "i18n", "title": "Hreflang Bidirectional",
                    "status": "pass",
                    "detail": f"All {checked} checked hreflang URLs have reciprocal return links",
                })
        else:
            checks.append({
                "id": "I2", "category": "i18n", "title": "Hreflang Bidirectional",
                "status": "skip", "detail": "No hreflang tags to check",
            })

        # ── I3: ISO code validation ──────────────────────────────
        if hreflangs:
            invalid_codes: list[str] = []
            for h in hreflangs:
                lang = h.get("hreflang", "")
                if lang == "x-default":
                    continue
                # hreflang can be "en" or "en-us" — extract base language
                base_lang = lang.split("-")[0].lower()
                if base_lang not in _ISO_639_1_CODES:
                    invalid_codes.append(lang)

            if invalid_codes:
                checks.append({
                    "id": "I3", "category": "i18n", "title": "ISO Code Validation",
                    "status": "warn",
                    "detail": f"Unrecognized language codes: {', '.join(invalid_codes)}",
                })
            else:
                checks.append({
                    "id": "I3", "category": "i18n", "title": "ISO Code Validation",
                    "status": "pass",
                    "detail": "All hreflang codes are valid ISO 639-1",
                })
        else:
            checks.append({
                "id": "I3", "category": "i18n", "title": "ISO Code Validation",
                "status": "skip", "detail": "No hreflang tags to validate",
            })

        # ── I4: URL qualification ────────────────────────────────
        if hreflangs:
            non_qualified: list[str] = []
            for h in hreflangs:
                href = h.get("href", "")
                if href and not href.startswith("http"):
                    non_qualified.append(f"{h.get('hreflang')}: {href}")

            if non_qualified:
                checks.append({
                    "id": "I4", "category": "i18n", "title": "URL Qualification",
                    "status": "warn",
                    "detail": f"{len(non_qualified)} hreflang URL(s) not fully qualified: {', '.join(non_qualified[:3])}",
                })
            else:
                checks.append({
                    "id": "I4", "category": "i18n", "title": "URL Qualification",
                    "status": "pass",
                    "detail": "All hreflang URLs are fully qualified (https://)",
                })
        else:
            checks.append({
                "id": "I4", "category": "i18n", "title": "URL Qualification",
                "status": "skip", "detail": "No hreflang tags to check",
            })

        # ── I5: Method consistency ───────────────────────────────
        methods_found: list[str] = []
        if hreflangs:
            methods_found.append("HTML <link> tags")

        # Check HTTP headers
        link_header = resp.headers.get("link", "")
        if link_header and "hreflang" in link_header.lower():
            methods_found.append("HTTP Link headers")

        # Check sitemap for hreflang (xhtml:link)
        if "hreflang" in html.lower() and "xmlns:xhtml" in html.lower():
            methods_found.append("Sitemap (inline)")

        if len(methods_found) > 1:
            checks.append({
                "id": "I5", "category": "i18n", "title": "Method Consistency",
                "status": "warn",
                "detail": f"hreflang declared in multiple methods: {', '.join(methods_found)} — use one method to avoid conflicts",
            })
        elif len(methods_found) == 1:
            checks.append({
                "id": "I5", "category": "i18n", "title": "Method Consistency",
                "status": "pass",
                "detail": f"hreflang declared in single method: {methods_found[0]}",
            })
        else:
            checks.append({
                "id": "I5", "category": "i18n", "title": "Method Consistency",
                "status": "skip",
                "detail": "No hreflang implementation detected",
            })

        # ── I6: Locale-adaptive detection ────────────────────────
        try:
            resp_en = client.get(url, headers={
                "User-Agent": "SEOAgent/1.0",
                "Accept-Language": "en-US,en;q=0.9",
            })
            resp_other = client.get(url, headers={
                "User-Agent": "SEOAgent/1.0",
                "Accept-Language": "ja,zh;q=0.9",
            })
            len_en = len(resp_en.text)
            len_other = len(resp_other.text)

            if len_en == 0:
                checks.append({
                    "id": "I6", "category": "i18n", "title": "Locale-Adaptive Detection",
                    "status": "skip", "detail": "Empty response for locale-adaptive check",
                })
            else:
                ratio = abs(len_en - len_other) / max(len_en, 1)
                if ratio > 0.3:
                    checks.append({
                        "id": "I6", "category": "i18n", "title": "Locale-Adaptive Detection",
                        "status": "warn",
                        "detail": (
                            f"Content differs significantly by Accept-Language "
                            f"(en: {len_en} chars, ja/zh: {len_other} chars, diff: {ratio:.0%}) — "
                            "consider separate URLs with hreflang instead"
                        ),
                    })
                else:
                    checks.append({
                        "id": "I6", "category": "i18n", "title": "Locale-Adaptive Detection",
                        "status": "pass",
                        "detail": f"Content consistent across Accept-Language headers (diff: {ratio:.0%})",
                    })
        except Exception as e:
            checks.append({
                "id": "I6", "category": "i18n", "title": "Locale-Adaptive Detection",
                "status": "skip", "detail": f"Could not compare locale-adaptive responses: {e}",
            })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }
