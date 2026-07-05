from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from ..config import settings


def technical_audit(url: str) -> dict:
    """Run comprehensive technical SEO audit on a URL."""
    if not url.startswith("http"):
        url = f"https://{url}"

    checks = []
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}) as client:
        # Fetch page
        resp = client.get(url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        final_url = str(resp.url)

        # A: Crawlability
        checks.extend(_check_crawlability(url, resp, soup))

        # B: Meta tags
        checks.extend(_check_meta_tags(soup))

        # C: Core Web Vitals (if API key available)
        cwv = _check_core_web_vitals(url)
        checks.extend(cwv)

        # D: Images & content
        checks.extend(_check_images_links(soup, url, client))

        # E: Schema markup
        checks.extend(_check_schema(soup))

        # F: Mobile
        checks.extend(_check_mobile(soup))

        # G: SPA rendering
        checks.extend(_check_spa(html))

        # H: E-E-A-T
        checks.extend(_check_eeat(soup))

        # I: i18n
        checks.extend(_check_i18n(soup))

    return {
        "url": url,
        "checks": checks,
        "summary": _summarize(checks),
    }


def _check_crawlability(url: str, resp, soup) -> list[dict]:
    checks = []

    # A1: HTTPS
    is_https = url.startswith("https://") or str(resp.url).startswith("https://")
    checks.append({
        "id": "A1", "category": "Crawlability", "title": "HTTPS",
        "status": "pass" if is_https else "fail",
        "detail": "Site uses HTTPS" if is_https else "Site does not use HTTPS",
    })

    # A2: robots.txt
    robots_text = ""
    try:
        with httpx.Client(timeout=10) as c:
            base = url.split("/")[0] + "//" + url.split("/")[2]
            r = c.get(f"{base}/robots.txt")
            if r.status_code == 200:
                robots_text = r.text
    except Exception:
        pass

    if robots_text:
        broad_disallow = bool(re.search(r"Disallow:\s*/\s*$", robots_text, re.MULTILINE))
        checks.append({
            "id": "A2", "category": "Crawlability", "title": "robots.txt",
            "status": "fail" if broad_disallow else "pass",
            "detail": "robots.txt found" + (" — blocks entire site!" if broad_disallow else ""),
        })
    else:
        checks.append({
            "id": "A2", "category": "Crawlability", "title": "robots.txt",
            "status": "warn", "detail": "No robots.txt found",
        })

    # A3: Sitemap
    sitemap_found = False
    if "Sitemap:" in robots_text:
        sitemap_found = True
    else:
        try:
            with httpx.Client(timeout=10) as c:
                base = url.split("/")[0] + "//" + url.split("/")[2]
                r = c.get(f"{base}/sitemap.xml")
                sitemap_found = r.status_code == 200
        except Exception:
            pass
    checks.append({
        "id": "A3", "category": "Crawlability", "title": "Sitemap",
        "status": "pass" if sitemap_found else "warn",
        "detail": "Sitemap found" if sitemap_found else "No sitemap detected",
    })

    # A4: noindex
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

    # A5: AI crawlers
    ai_bots = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"]
    blocked_bots = []
    if robots_text:
        for bot in ai_bots:
            if re.search(rf"User-agent:\s*{bot}.*?Disallow:\s*/", robots_text, re.DOTALL | re.IGNORECASE):
                blocked_bots.append(bot)
    checks.append({
        "id": "A5", "category": "Crawlability", "title": "AI Crawlers",
        "status": "fail" if blocked_bots else "pass",
        "detail": f"Blocked: {', '.join(blocked_bots)}" if blocked_bots else "AI crawlers not blocked",
    })

    return checks


def _check_meta_tags(soup) -> list[dict]:
    checks = []

    # B1: Title
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    title_len = len(title)
    if not title:
        status, detail = "fail", "No title tag found"
    elif 30 <= title_len <= 60:
        status, detail = "pass", f"Title: {title} ({title_len} chars)"
    else:
        status, detail = "warn", f"Title length {title_len} chars (target 30-60): {title}"
    checks.append({"id": "B1", "category": "Meta Tags", "title": "Title Tag", "status": status, "detail": detail})

    # B2: Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc_text = meta_desc.get("content", "").strip() if meta_desc else ""
    desc_len = len(desc_text)
    if not desc_text:
        status, detail = "fail", "No meta description found"
    elif 110 <= desc_len <= 160:
        status, detail = "pass", f"Meta description: {desc_len} chars"
    else:
        status, detail = "warn", f"Meta description length {desc_len} chars (target 110-160)"
    checks.append({"id": "B2", "category": "Meta Tags", "title": "Meta Description", "status": status, "detail": detail})

    # B3: H1
    h1s = soup.find_all("h1")
    h1_count = len(h1s)
    if h1_count == 1:
        status, detail = "pass", f"H1: {h1s[0].get_text(strip=True)[:80]}"
    elif h1_count == 0:
        status, detail = "fail", "No H1 tag found"
    else:
        status, detail = "warn", f"Found {h1_count} H1 tags (should be exactly 1)"
    checks.append({"id": "B3", "category": "Meta Tags", "title": "H1 Tag", "status": status, "detail": detail})

    # B4: Duplicate title / description (title == meta description on same page)
    if title and desc_text:
        title_normalized = title.lower().strip()
        desc_normalized = desc_text.lower().strip()
        if title_normalized == desc_normalized:
            status, detail = "warn", "Title and meta description are identical — Google may pick wrong snippet"
        else:
            status, detail = "pass", "Title and meta description are distinct"
    else:
        status, detail = "skip", "Cannot compare — title or description missing"
    checks.append({"id": "B4", "category": "Meta Tags", "title": "Duplicate Title/Desc", "status": status, "detail": detail})

    return checks


def _check_core_web_vitals(url: str) -> list[dict]:
    checks = []
    if not settings.pagespeed_api_key:
        checks.append({
            "id": "C1", "category": "Core Web Vitals", "title": "LCP / CLS / INP",
            "status": "skip", "detail": "PageSpeed API key not configured",
        })
        return checks

    try:
        with httpx.Client(timeout=60) as client:
            r = client.get(
                f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}"
                f"&key={settings.pagespeed_api_key}&strategy=mobile&category=PERFORMANCE"
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
            "status": "skip", "detail": f"Failed to fetch: {e}",
        })

    return checks


def _check_images_links(soup, base_url: str, client) -> list[dict]:
    checks = []

    # D1: Image alt text
    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt", "").strip()]
    alt_pct = len(missing_alt) / max(len(images), 1)
    if not images:
        status, detail = "skip", "No images found"
    elif alt_pct > 0.5:
        status, detail = "fail", f"{len(missing_alt)}/{len(images)} images missing alt text"
    elif alt_pct > 0:
        status, detail = "warn", f"{len(missing_alt)}/{len(images)} images missing alt text"
    else:
        status, detail = "pass", f"All {len(images)} images have alt text"
    checks.append({"id": "D1", "category": "Images", "title": "Image Alt Text", "status": status, "detail": detail})

    # D2: Image dimensions
    missing_dims = [img for img in images if not img.get("width") or not img.get("height")]
    if images:
        dim_pct = len(missing_dims) / max(len(images), 1)
        if dim_pct > 0.5:
            status, detail = "warn", f"{len(missing_dims)}/{len(images)} images missing explicit width/height (CLS risk)"
        else:
            status, detail = "pass", f"{len(images) - len(missing_dims)}/{len(images)} images have dimensions"
        checks.append({"id": "D2", "category": "Images", "title": "Image Dimensions", "status": status, "detail": detail})

    # D3: Broken links (check up to 30 internal links)
    internal_links = []
    base_domain = base_url.split("/")[2]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") or base_domain in href:
            full = href if href.startswith("http") else f"{base_url.rstrip('/')}/{href.lstrip('/')}"
            if full.startswith("http") and base_domain in full:
                internal_links.append(full)

    broken = []
    for link in internal_links[:30]:
        try:
            r = client.head(link, timeout=10)
            if r.status_code == 404:
                broken.append(link)
        except Exception:
            pass

    if broken:
        checks.append({"id": "D3", "category": "Links", "title": "Broken Links", "status": "fail", "detail": f"{len(broken)} broken internal links found"})
    else:
        checks.append({"id": "D3", "category": "Links", "title": "Broken Links", "status": "pass", "detail": f"Checked {min(len(internal_links), 30)} internal links, none broken"})

    return checks


def _check_schema(soup) -> list[dict]:
    checks = []

    # E1: Schema present
    jsonld = soup.find_all("script", attrs={"type": "application/ld+json"})
    microdata = soup.find_all(attrs={"itemscope": True})
    has_schema = bool(jsonld) or bool(microdata)
    checks.append({
        "id": "E1", "category": "Schema", "title": "Schema Present",
        "status": "pass" if has_schema else "warn",
        "detail": f"Found {len(jsonld)} JSON-LD blocks, {len(microdata)} microdata items" if has_schema else "No structured data detected",
    })

    if jsonld:
        # E2: Schema type
        types_found = set()
        valid = True
        for block in jsonld:
            try:
                data = json.loads(block.string)
                if isinstance(data, list):
                    for item in data:
                        if "@type" in item:
                            types_found.add(item["@type"])
                elif "@type" in data:
                    types_found.add(data["@type"])
            except (json.JSONDecodeError, TypeError):
                valid = False

        checks.append({
            "id": "E2", "category": "Schema", "title": "Schema Type",
            "status": "pass" if types_found else "warn",
            "detail": f"Types: {', '.join(types_found)}" if types_found else "Could not determine schema type",
        })

        # E3: Valid JSON
        checks.append({
            "id": "E3", "category": "Schema", "title": "Schema Valid JSON",
            "status": "pass" if valid else "fail",
            "detail": "All JSON-LD blocks are valid" if valid else "Some JSON-LD blocks have syntax errors",
        })

    return checks


def _check_mobile(soup) -> list[dict]:
    checks = []

    # F1: Viewport
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport and "width=device-width" in (viewport.get("content") or ""):
        status, detail = "pass", "Viewport meta tag correctly set"
    else:
        status, detail = "fail", "Missing or incorrect viewport meta tag"
    checks.append({"id": "F1", "category": "Mobile", "title": "Viewport", "status": status, "detail": detail})

    # F2: Horizontal scroll
    fixed_width = soup.find_all(style=re.compile(r"width:\s*\d{3,}px"))
    fixed_tables = soup.find_all("table", attrs={"width": re.compile(r"\d{3,}")})
    if fixed_width or fixed_tables:
        checks.append({
            "id": "F2", "category": "Mobile", "title": "Horizontal Scroll",
            "status": "warn",
            "detail": f"Found {len(fixed_width)} fixed-width elements and {len(fixed_tables)} fixed-width tables",
        })
    else:
        checks.append({"id": "F2", "category": "Mobile", "title": "Horizontal Scroll", "status": "pass", "detail": "No obvious horizontal scroll causes"})

    return checks


def _check_spa(html: str) -> list[dict]:
    checks = []

    # G1: SPA rendering
    spa_frameworks = {
        "Next.js": "__NEXT_DATA__" in html or "_next" in html,
        "Nuxt": "__NUXT__" in html or "_nuxt" in html,
        "React": 'data-reactroot' in html or 'react-root' in html,
        "Vue": 'data-v-' in html or 'vue-app' in html,
        "SvelteKit": 'data-sveltekit' in html,
    }
    detected_spa = [fw for fw, detected in spa_frameworks.items() if detected]

    # Check for visible content in raw HTML
    visible_text = re.sub(r"<[^>]+>", " ", html)
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    has_content = len(visible_text) > 200

    if detected_spa and not has_content:
        status = "fail"
        detail = f"SPA framework detected ({', '.join(detected_spa)}) but minimal visible content in raw HTML — AI crawlers may see blank page"
    elif detected_spa:
        status = "warn"
        detail = f"SPA framework detected ({', '.join(detected_spa)}) — verify content is server-rendered"
    else:
        status = "pass"
        detail = "No SPA framework detected, content visible in raw HTML"

    checks.append({"id": "G1", "category": "SPA", "title": "Server-side Rendering", "status": status, "detail": detail})
    return checks


def _check_eeat(soup) -> list[dict]:
    checks = []

    # H1: Author
    author = None
    # Check JSON-LD
    for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(block.string)
            if isinstance(data, dict) and data.get("author"):
                author = data["author"].get("name", "") if isinstance(data["author"], dict) else data["author"]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("author"):
                        author = item["author"].get("name", "") if isinstance(item["author"], dict) else item["author"]
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
    elif author.lower() in generic_names:
        status, detail = "warn", f"Generic author name: '{author}' — use a real person's name"
    else:
        status, detail = "pass", f"Author: {author}"
    checks.append({"id": "H1", "category": "E-E-A-T", "title": "Author", "status": status, "detail": detail})

    # H2: Dates
    published = None
    modified = None
    for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(block.string)
            if isinstance(data, dict):
                published = published or data.get("datePublished")
                modified = modified or data.get("dateModified")
        except (json.JSONDecodeError, TypeError):
            pass

    if not published:
        meta_pub = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_pub:
            published = meta_pub.get("content", "")

    if not modified:
        meta_mod = soup.find("meta", attrs={"property": "article:modified_time"})
        if meta_mod:
            modified = meta_mod.get("content", "")

    if published and modified:
        status, detail = "pass", f"Published: {published}, Modified: {modified}"
    elif published:
        status, detail = "warn", f"Published: {published} but no modified date"
    else:
        status, detail = "warn", "No published or modified dates found"
    checks.append({"id": "H2", "category": "E-E-A-T", "title": "Dates", "status": status, "detail": detail})

    return checks


def _check_i18n(soup) -> list[dict]:
    checks = []

    # I1: hreflang
    hreflangs = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
    lang_switchers = soup.find_all(class_=re.compile(r"lang|language|locale", re.I))

    if hreflangs:
        has_x_default = any(h.get("hreflang") == "x-default" for h in hreflangs)
        status = "pass"
        detail = f"Found {len(hreflangs)} hreflang tags" + (" with x-default" if has_x_default else " (missing x-default)")
    elif lang_switchers:
        status = "warn"
        detail = "Language switcher detected but no hreflang tags"
    else:
        status = "skip"
        detail = "No multilingual signals detected"

    checks.append({"id": "I1", "category": "i18n", "title": "Hreflang", "status": status, "detail": detail})
    return checks


def _summarize(checks: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return counts
