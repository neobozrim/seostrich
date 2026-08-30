from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from ..config import settings


def render_and_compare(url: str, wait_seconds: int = 5) -> dict:
    """Analyse what a crawler sees without JavaScript execution.

    Fetches the raw HTML via httpx (no browser) and inspects whether critical
    SEO elements are present in the initial response.  Detects SPA frameworks,
    SSR markers, and reports a parity score indicating how much content a
    JavaScript-incapable crawler would miss.

    NOTE: ``wait_seconds`` is accepted for interface compatibility but is not
    used — there is no Playwright / headless browser dependency.
    """
    if not url.startswith("http"):
        url = f"https://{url}"

    rendering_issues: list[str] = []
    recommendations: list[str] = []

    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "SEOAgent/1.0"},
    ) as client:
        resp = client.get(url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

    # ── Extract visible text from raw HTML ───────────────────────
    raw_soup = BeautifulSoup(html, "html.parser")
    for el in raw_soup.find_all(["script", "style", "noscript"]):
        el.decompose()
    visible_text = raw_soup.get_text(separator=" ", strip=True)
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    word_count = len(visible_text.split())

    raw_html_has_content = word_count > 50

    # ── SPA / SSR framework detection ───────────────────────────
    spa_indicators: dict[str, bool] = {
        "Next.js": "__NEXT_DATA__" in html or "_next" in html,
        "Nuxt": "__NUXT__" in html or "_nuxt" in html,
        "React (CSR)": bool(re.search(r'<div\s+id=["\']root["\']', html)) and word_count < 50,
        "Vue (CSR)": bool(re.search(r'<div\s+id=["\']app["\']', html)) and word_count < 50,
        "Svelte": "data-sveltekit" in html,
        "Angular": bool(re.search(r"<app-root", html)),
    }
    spa_framework_detected = any(spa_indicators.values())

    ssr_markers: dict[str, bool] = {
        "__NEXT_DATA__": "__NEXT_DATA__" in html,
        "__NUXT__": "__NUXT__" in html,
        "data-reactroot": 'data-reactroot' in html,
        "data-server-rendered": 'data-server-rendered' in html,
    }
    ssr_detected = any(ssr_markers.values())

    # ── Check critical SEO elements in raw HTML ──────────────────
    critical_elements: dict[str, dict] = {}

    # Title
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    critical_elements["title"] = {
        "present": bool(title),
        "value": title[:100] if title else "",
    }
    if not title:
        rendering_issues.append("Missing <title> in raw HTML")
        recommendations.append("Ensure title is rendered server-side or pre-rendered")

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc_text = meta_desc.get("content", "").strip() if meta_desc else ""
    critical_elements["meta_description"] = {
        "present": bool(desc_text),
        "value": desc_text[:200] if desc_text else "",
    }
    if not desc_text:
        rendering_issues.append("Missing meta description in raw HTML")
        recommendations.append("Add meta description that is present in the initial HTML response")

    # Canonical
    canonical = soup.find("link", attrs={"rel": "canonical"})
    canonical_href = canonical.get("href", "") if canonical else ""
    critical_elements["canonical"] = {
        "present": bool(canonical_href),
        "value": canonical_href,
    }
    if not canonical_href:
        rendering_issues.append("Missing canonical link in raw HTML")
        recommendations.append("Add <link rel='canonical'> in the server-rendered HTML")

    # H1
    h1s = soup.find_all("h1")
    critical_elements["h1"] = {
        "present": len(h1s) > 0,
        "count": len(h1s),
        "value": h1s[0].get_text(strip=True)[:100] if h1s else "",
    }
    if not h1s:
        rendering_issues.append("No H1 tag in raw HTML")
        recommendations.append("Ensure H1 is part of the server-rendered markup")

    # Main content (body text)
    critical_elements["main_content"] = {
        "present": raw_html_has_content,
        "word_count": word_count,
    }
    if not raw_html_has_content:
        rendering_issues.append(f"Very little visible text in raw HTML ({word_count} words)")
        recommendations.append(
            "Implement server-side rendering (SSR) or static generation (SSG) "
            "so crawlers receive full content without executing JavaScript"
        )

    # hreflang
    hreflangs = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
    critical_elements["hreflang"] = {
        "present": len(hreflangs) > 0,
        "count": len(hreflangs),
    }

    # Structured data
    jsonld = soup.find_all("script", attrs={"type": "application/ld+json"})
    critical_elements["structured_data"] = {
        "present": len(jsonld) > 0,
        "count": len(jsonld),
    }
    if not jsonld:
        rendering_issues.append("No JSON-LD structured data in raw HTML")

    # OG tags
    og_title = soup.find("meta", attrs={"property": "og:title"})
    critical_elements["og_tags"] = {
        "present": bool(og_title),
    }

    # ── Parity score ─────────────────────────────────────────────
    # Score based on how many critical elements are present in the raw HTML
    total_elements = len(critical_elements)
    present_count = sum(1 for v in critical_elements.values() if v.get("present"))
    parity_score = int((present_count / max(total_elements, 1)) * 100)

    # Adjust: if SSR detected, boost score
    if ssr_detected:
        parity_score = min(100, parity_score + 10)
    # If SPA without SSR, penalise
    if spa_framework_detected and not ssr_detected:
        parity_score = max(0, parity_score - 15)

    # ── Build recommendations based on findings ──────────────────
    if spa_framework_detected and not ssr_detected:
        detected_spa = [name for name, found in spa_indicators.items() if found]
        recommendations.insert(0, (
            f"SPA framework detected ({', '.join(detected_spa)}) without SSR — "
            "AI crawlers and search engines may see a blank or near-blank page. "
            "Enable SSR/SSG or use a pre-rendering service."
        ))

    if ssr_detected:
        detected_ssr = [name for name, found in ssr_markers.items() if found]
        recommendations.insert(0, (
            f"SSR markers found ({', '.join(detected_ssr)}) — crawlers should receive full content."
        ))

    # Deduplicate recommendations while preserving order
    seen: set[str] = set()
    unique_recs: list[str] = []
    for r in recommendations:
        if r not in seen:
            seen.add(r)
            unique_recs.append(r)
    recommendations = unique_recs

    return {
        "url": url,
        "raw_html_analysis": {
            "raw_html_has_content": raw_html_has_content,
            "word_count": word_count,
            "spa_framework_detected": spa_framework_detected,
            "spa_frameworks": [name for name, found in spa_indicators.items() if found],
            "ssr_detected": ssr_detected,
            "ssr_markers": [name for name, found in ssr_markers.items() if found],
            "critical_elements": critical_elements,
        },
        "rendering_issues": rendering_issues,
        "parity_score": parity_score,
        "recommendations": recommendations,
    }
