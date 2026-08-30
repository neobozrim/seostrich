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


def audit_performance(url: str) -> dict:
    """Run performance & security-header audit (C1–C9) on the given URL."""
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
        headers = resp.headers

        # ── C1–C3: Core Web Vitals (PageSpeed API) ───────────────
        if settings.pagespeed_api_key:
            try:
                r = client.get(
                    f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
                    f"?url={url}&key={settings.pagespeed_api_key}"
                    f"&strategy=mobile&category=PERFORMANCE",
                    timeout=60,
                )
                data = r.json()
                audits = data.get("lighthouseResult", {}).get("audits", {})

                lcp = audits.get("largest-contentful-paint", {}).get("numericValue", 0) / 1000
                cls = audits.get("cumulative-layout-shift", {}).get("numericValue", 0)
                inp = audits.get("interaction-to-next-paint", {}).get("numericValue", 0)

                lcp_status = "pass" if lcp <= 2.5 else ("warn" if lcp <= 4.0 else "fail")
                cls_status = "pass" if cls <= 0.1 else ("warn" if cls <= 0.25 else "fail")
                inp_status = "pass" if inp <= 200 else ("warn" if inp <= 500 else "fail")

                checks.append({"id": "C1", "category": "Core Web Vitals", "title": "LCP", "status": lcp_status, "detail": f"{lcp:.1f}s (target ≤2.5s)"})
                checks.append({"id": "C2", "category": "Core Web Vitals", "title": "CLS", "status": cls_status, "detail": f"{cls:.3f} (target ≤0.1)"})
                checks.append({"id": "C3", "category": "Core Web Vitals", "title": "INP", "status": inp_status, "detail": f"{inp:.0f}ms (target ≤200ms)"})
            except Exception as e:
                checks.append({
                    "id": "C1", "category": "Core Web Vitals", "title": "CWV Error",
                    "status": "skip", "detail": f"Failed to fetch PageSpeed data: {e}",
                })
                checks.append({"id": "C2", "category": "Core Web Vitals", "title": "CLS", "status": "skip", "detail": "PageSpeed unavailable"})
                checks.append({"id": "C3", "category": "Core Web Vitals", "title": "INP", "status": "skip", "detail": "PageSpeed unavailable"})
        else:
            checks.append({
                "id": "C1", "category": "Core Web Vitals", "title": "LCP / CLS / INP",
                "status": "skip", "detail": "PageSpeed API key not configured",
            })
            checks.append({"id": "C2", "category": "Core Web Vitals", "title": "CLS", "status": "skip", "detail": "PageSpeed API key not configured"})
            checks.append({"id": "C3", "category": "Core Web Vitals", "title": "INP", "status": "skip", "detail": "PageSpeed API key not configured"})

        # ── C4: HSTS header ──────────────────────────────────────
        hsts = headers.get("strict-transport-security", "")
        if hsts:
            max_age_match = re.search(r"max-age=(\d+)", hsts, re.I)
            max_age = int(max_age_match.group(1)) if max_age_match else 0
            if max_age > 0:
                status, detail = "pass", f"HSTS present, max-age={max_age}"
            else:
                status, detail = "warn", f"HSTS present but max-age=0: {hsts}"
        else:
            status, detail = "warn", "Strict-Transport-Security header not set"
        checks.append({
            "id": "C4", "category": "Security Headers", "title": "HSTS",
            "status": status, "detail": detail,
        })

        # ── C5: Content-Security-Policy ──────────────────────────
        csp = headers.get("content-security-policy", "")
        if csp:
            status, detail = "pass", "Content-Security-Policy header present"
        else:
            status, detail = "warn", "Content-Security-Policy header not set (recommended)"
        checks.append({
            "id": "C5", "category": "Security Headers", "title": "Content-Security-Policy",
            "status": status, "detail": detail,
        })

        # ── C6: X-Frame-Options ──────────────────────────────────
        xfo = headers.get("x-frame-options", "")
        if xfo:
            status, detail = "pass", f"X-Frame-Options: {xfo}"
        else:
            status, detail = "warn", "X-Frame-Options header not set"
        checks.append({
            "id": "C6", "category": "Security Headers", "title": "X-Frame-Options",
            "status": status, "detail": detail,
        })

        # ── C7: Mixed content ────────────────────────────────────
        is_https_page = str(resp.url).startswith("https://")
        if is_https_page:
            http_refs: list[str] = []
            for tag in soup.find_all(["img", "script", "link", "source", "iframe"]):
                for attr in ("src", "href"):
                    val = tag.get(attr, "")
                    if isinstance(val, str) and val.startswith("http://"):
                        http_refs.append(f"<{tag.name} {attr}=\"{val[:60]}…\">")
            if http_refs:
                checks.append({
                    "id": "C7", "category": "Security", "title": "Mixed Content",
                    "status": "fail",
                    "detail": f"Page is HTTPS but loads {len(http_refs)} HTTP resource(s): {http_refs[0]}" + (
                        f" (+{len(http_refs) - 1} more)" if len(http_refs) > 1 else ""
                    ),
                })
            else:
                checks.append({
                    "id": "C7", "category": "Security", "title": "Mixed Content",
                    "status": "pass",
                    "detail": "No mixed-content references found on HTTPS page",
                })
        else:
            checks.append({
                "id": "C7", "category": "Security", "title": "Mixed Content",
                "status": "skip",
                "detail": "Page is not HTTPS — mixed-content check skipped",
            })

        # ── C8: Resource loading ─────────────────────────────────
        images = soup.find_all("img")
        scripts = soup.find_all("script", src=True)
        stylesheets = soup.find_all("link", rel="stylesheet")
        total_resources = len(images) + len(scripts) + len(stylesheets)
        if total_resources > 100:
            status, detail = "warn", (
                f"{total_resources} resources ({len(images)} images, "
                f"{len(scripts)} scripts, {len(stylesheets)} stylesheets) — consider reducing"
            )
        else:
            status, detail = "pass", (
                f"{total_resources} resources ({len(images)} images, "
                f"{len(scripts)} scripts, {len(stylesheets)} stylesheets)"
            )
        checks.append({
            "id": "C8", "category": "Performance", "title": "Resource Count",
            "status": status, "detail": detail,
        })

        # ── C9: Render-blocking resources ────────────────────────
        head = soup.find("head")
        render_blocking = 0
        if head:
            for link in head.find_all("link", rel="stylesheet"):
                # Preload / async styles are not render-blocking
                rel_val = " ".join(link.get("rel", []))
                if "preload" not in rel_val:
                    render_blocking += 1
            for script in head.find_all("script", src=True):
                if not script.get("async") and not script.get("defer"):
                    render_blocking += 1
        if render_blocking > 5:
            status, detail = "warn", f"{render_blocking} render-blocking CSS/JS resources in <head>"
        else:
            status, detail = "pass", f"{render_blocking} render-blocking resources in <head> (≤5 is fine)"
        checks.append({
            "id": "C9", "category": "Performance", "title": "Render-Blocking Resources",
            "status": status, "detail": detail,
        })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }
