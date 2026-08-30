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


def audit_crawlability(url: str) -> dict:
    """Run crawlability audit (A1–A10) on the given URL."""
    if not url.startswith("http"):
        url = f"https://{url}"

    base = url.split("/")[0] + "//" + url.split("/")[2]
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

        # ── A1: HTTPS ──────────────────────────────────────────────
        is_https = url.startswith("https://") or final_url.startswith("https://")
        checks.append({
            "id": "A1", "category": "Crawlability", "title": "HTTPS",
            "status": "pass" if is_https else "fail",
            "detail": "Site uses HTTPS" if is_https else "Site does not use HTTPS",
        })

        # ── A2: robots.txt ─────────────────────────────────────────
        robots_text = ""
        try:
            r = client.get(f"{base}/robots.txt")
            if r.status_code == 200:
                robots_text = r.text
        except Exception:
            pass

        if robots_text:
            broad_disallow = bool(re.search(r"Disallow:\s*/\s*$", robots_text, re.MULTILINE))
            # Detect blocked resource patterns
            blocked_resources = []
            for pattern in re.finditer(r"Disallow:\s*(.+)", robots_text):
                path = pattern.group(1).strip()
                if re.search(r"\*\.(css|js|jpg|jpeg|png|gif|svg|webp|woff|woff2|ttf)", path, re.I):
                    blocked_resources.append(path)
                elif re.search(r"/(assets|static|public|wp-content/(themes|plugins))", path, re.I):
                    blocked_resources.append(path)
            # Sitemap directive
            sitemap_directives = re.findall(r"Sitemap:\s*(\S+)", robots_text, re.I)
            # AI crawler tokens
            ai_bots = [
                "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended",
                "CCBot", "ChatGPT-User", "anthropic-ai", "Perplexity-User",
                "Bytespider", "Applebot-Extended", "Meta-ExternalAgent",
            ]
            blocked_bots: list[str] = []
            allowed_bots: list[str] = []
            for bot in ai_bots:
                if re.search(
                    rf"User-agent:\s*{re.escape(bot)}.*?Disallow:\s*/\s*$",
                    robots_text, re.DOTALL | re.IGNORECASE | re.MULTILINE,
                ):
                    blocked_bots.append(bot)
                else:
                    allowed_bots.append(bot)

            detail_parts = ["robots.txt found"]
            if broad_disallow:
                detail_parts.append("blocks entire site!")
            if blocked_resources:
                detail_parts.append(f"blocks {len(blocked_resources)} resource path(s)")
            if sitemap_directives:
                detail_parts.append(f"Sitemap: {', '.join(sitemap_directives)}")
            else:
                detail_parts.append("no Sitemap: directive")
            detail_parts.append(f"AI bots blocked: {len(blocked_bots)}/{len(ai_bots)}")

            status = "fail" if broad_disallow else ("warn" if blocked_resources or blocked_bots else "pass")
            checks.append({
                "id": "A2", "category": "Crawlability", "title": "robots.txt",
                "status": status,
                "detail": " — ".join(detail_parts),
            })
        else:
            blocked_bots = []
            allowed_bots = []
            sitemap_directives = []
            blocked_resources = []
            checks.append({
                "id": "A2", "category": "Crawlability", "title": "robots.txt",
                "status": "warn", "detail": "No robots.txt found",
            })

        # ── A3: Sitemap presence ───────────────────────────────────
        sitemap_found = bool(sitemap_directives)
        if not sitemap_found:
            try:
                r = client.get(f"{base}/sitemap.xml")
                sitemap_found = r.status_code == 200
            except Exception:
                pass
        checks.append({
            "id": "A3", "category": "Crawlability", "title": "Sitemap",
            "status": "pass" if sitemap_found else "warn",
            "detail": "Sitemap found" if sitemap_found else "No sitemap detected",
        })

        # ── A4: noindex ───────────────────────────────────────────
        meta_robots = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        has_noindex = False
        if meta_robots:
            content = (meta_robots.get("content") or "").lower()
            has_noindex = "noindex" in content
        checks.append({
            "id": "A4", "category": "Crawlability", "title": "Noindex",
            "status": "fail" if has_noindex else "pass",
            "detail": "Page is marked noindex!" if has_noindex else "No noindex directive",
        })

        # ── A5: Canonical tag ─────────────────────────────────────
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        if canonical_tag:
            canonical_href = canonical_tag.get("href", "")
            is_absolute = canonical_href.startswith("http")
            is_self_ref = canonical_href.rstrip("/") == url.rstrip("/") or canonical_href.rstrip("/") == final_url.rstrip("/")
            conflict = has_noindex and canonical_href and not is_self_ref
            if conflict:
                status, detail = "warn", (
                    f"Canonical points to {canonical_href} but page is noindex — "
                    "conflicting signals"
                )
            elif not is_absolute:
                status, detail = "warn", f"Canonical is relative URL: {canonical_href}"
            elif is_self_ref:
                status, detail = "pass", f"Self-referencing canonical: {canonical_href}"
            else:
                status, detail = "pass", f"Canonical: {canonical_href}"
        else:
            status, detail = "warn", "No canonical tag found"
        checks.append({
            "id": "A5", "category": "Crawlability", "title": "Canonical Tag",
            "status": status, "detail": detail,
        })

        # ── A6: Redirect detection ────────────────────────────────
        redirected = final_url != url
        if redirected:
            # Determine redirect type from history
            redirect_chain = []
            if hasattr(resp, "history") and resp.history:
                for r in resp.history:
                    redirect_chain.append(f"{r.status_code} → {r.headers.get('location', '?')}")
            chain_str = " → ".join(redirect_chain) if redirect_chain else f"{url} → {final_url}"
            checks.append({
                "id": "A6", "category": "Crawlability", "title": "Redirect Detection",
                "status": "warn",
                "detail": f"URL redirected: {chain_str}",
            })
        else:
            checks.append({
                "id": "A6", "category": "Crawlability", "title": "Redirect Detection",
                "status": "pass",
                "detail": "No redirect — URL resolved directly",
            })

        # ── A7: AI crawler blocking summary ───────────────────────
        ai_bots_full = [
            "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended",
            "CCBot", "ChatGPT-User", "anthropic-ai", "Perplexity-User",
            "Bytespider", "Applebot-Extended", "Meta-ExternalAgent",
        ]
        if robots_text:
            blocked_list = []
            allowed_list = []
            for bot in ai_bots_full:
                if re.search(
                    rf"User-agent:\s*{re.escape(bot)}.*?Disallow:\s*/\s*$",
                    robots_text, re.DOTALL | re.IGNORECASE | re.MULTILINE,
                ):
                    blocked_list.append(bot)
                else:
                    allowed_list.append(bot)
            if blocked_list and not allowed_list:
                status = "fail"
            elif blocked_list:
                status = "warn"
            else:
                status = "pass"
            detail = f"Blocked: {', '.join(blocked_list) or 'none'} | Allowed: {', '.join(allowed_list) or 'none'}"
        else:
            status = "skip"
            detail = "No robots.txt to analyse"
        checks.append({
            "id": "A7", "category": "Crawlability", "title": "AI Crawler Blocking Summary",
            "status": status, "detail": detail,
        })

        # ── A8: Internal link crawlability ────────────────────────
        a_links = soup.find_all("a", href=True)
        crawlable_count = len(a_links)
        # Non-crawlable interactive elements
        non_crawlable = []
        for tag_name in ("span", "div", "button"):
            for el in soup.find_all(tag_name):
                if el.get("onclick") or el.get("data-href") or el.get("data-url"):
                    non_crawlable.append(el.name)
        total_nav = crawlable_count + len(non_crawlable)
        if total_nav == 0:
            pct = 0.0
        else:
            pct = (crawlable_count / total_nav) * 100
        if pct >= 90:
            status = "pass"
        elif pct >= 60:
            status = "warn"
        else:
            status = "fail"
        checks.append({
            "id": "A8", "category": "Crawlability", "title": "Internal Link Crawlability",
            "status": status,
            "detail": (
                f"{crawlable_count}/{total_nav} ({pct:.0f}%) navigation elements are "
                f"<a href> links; {len(non_crawlable)} non-crawlable interactive elements"
            ),
        })

        # ── A9: Open/closed index ratio ───────────────────────────
        # Estimate from sitemap + current page noindex
        if sitemap_found:
            sitemap_page_count = None
            try:
                r = client.get(f"{base}/sitemap.xml")
                if r.status_code == 200:
                    sitemap_soup = BeautifulSoup(r.text, "html.parser")
                    sitemap_page_count = len(sitemap_soup.find_all("url"))
                    if sitemap_page_count == 0:
                        # Maybe sitemap index — count <sitemap> entries
                        sitemap_page_count = len(sitemap_soup.find_all("sitemap"))
            except Exception:
                pass
            if sitemap_page_count and sitemap_page_count > 0:
                detail = f"Sitemap lists {sitemap_page_count} URLs; current page noindex={'yes' if has_noindex else 'no'}"
                status = "pass"
            else:
                detail = "Sitemap found but could not count URLs"
                status = "skip"
        else:
            detail = "No sitemap available for index ratio estimate"
            status = "skip"
        checks.append({
            "id": "A9", "category": "Crawlability", "title": "Open/Closed Index Ratio",
            "status": status, "detail": detail,
        })

        # ── A10: robots.txt resource blocking ─────────────────────
        if robots_text:
            resource_patterns = {
                "CSS": r"\.css",
                "JS": r"\.js",
                "Fonts": r"\.(woff2?|ttf|eot|otf)",
                "Images": r"\.(jpg|jpeg|png|gif|svg|webp|avif|ico)",
            }
            blocked_categories: list[str] = []
            for cat, pat in resource_patterns.items():
                disallow_lines = re.findall(r"Disallow:\s*(.+)", robots_text)
                for line in disallow_lines:
                    if re.search(pat, line, re.I) or re.search(r"/(assets|static|public)/", line, re.I):
                        blocked_categories.append(cat)
                        break
            if blocked_categories:
                status = "warn"
                detail = f"robots.txt blocks resources: {', '.join(blocked_categories)}"
            else:
                status = "pass"
                detail = "No CSS/JS/font/image paths blocked in robots.txt"
        else:
            status = "skip"
            detail = "No robots.txt to check resource blocking"
        checks.append({
            "id": "A10", "category": "Crawlability", "title": "robots.txt Resource Blocking",
            "status": status, "detail": detail,
        })

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
        "robots_txt": robots_text,
    }
