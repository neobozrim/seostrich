from __future__ import annotations

import re
from collections import deque
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


_GENERIC_ANCHORS = {
    "click here",
    "here",
    "read more",
    "learn more",
    "more",
    "this",
    "link",
    "go",
    "continue",
    "see more",
    "view more",
}


def internal_link_audit(start_url: str, max_pages: int = 50, max_depth: int = 3) -> dict:
    """BFS crawl from start_url and audit internal link structure."""
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}"

    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc.lower()
    issues: list[str] = []

    visited: set[str] = set()
    # link_graph: source -> list of (target, anchor_text, is_crawlable)
    link_graph: dict[str, list[tuple[str, str, bool]]] = {}
    # depth tracking
    page_depth: dict[str, int] = {start_url: 0}
    # pages that are linked to
    linked_to: set[str] = set()
    # total link counters
    total_internal_links = 0
    generic_anchor_count = 0
    total_anchor_count = 0
    non_crawlable_count = 0
    total_nav_elements = 0

    # Fetch robots.txt disallow rules
    disallow_patterns: list[re.Pattern] = []
    try:
        with httpx.Client(
            timeout=15, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
        ) as client:
            base_url = f"{parsed_start.scheme}://{domain}"
            r = client.get(f"{base_url}/robots.txt")
            if r.status_code == 200:
                in_relevant_block = False
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("user-agent:"):
                        agent = line.split(":", 1)[1].strip()
                        in_relevant_block = agent == "*" or agent.lower() == "seoagent"
                    elif in_relevant_block and line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        if path:
                            disallow_patterns.append(
                                re.compile(re.escape(path).replace(r"\*", ".*"))
                            )
    except Exception:
        pass

    def is_disallowed(path: str) -> bool:
        for pat in disallow_patterns:
            if pat.search(path):
                return True
        return False

    def normalize_url(u: str) -> str:
        """Strip fragment and trailing slash for consistent comparison."""
        p = urlparse(u)
        # Remove fragment, normalize path
        path = p.path.rstrip("/") or "/"
        return f"{p.scheme}://{p.netloc}{path}"

    queue: deque[str] = deque([start_url])

    with httpx.Client(
        timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
    ) as client:
        while queue and len(visited) < max_pages:
            current_url = queue.popleft()
            norm = normalize_url(current_url)

            if norm in visited:
                continue

            current_depth = page_depth.get(current_url, page_depth.get(norm, 0))
            if current_depth > max_depth:
                continue

            parsed_current = urlparse(current_url)
            if parsed_current.netloc.lower() != domain:
                continue

            if is_disallowed(parsed_current.path):
                continue

            visited.add(norm)

            try:
                resp = client.get(current_url)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    continue
                soup = BeautifulSoup(resp.text[:200_000], "html.parser")
            except Exception:
                continue

            page_links: list[tuple[str, str, bool]] = []

            # Find all <a href> links
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(current_url, href)
                parsed_link = urlparse(full_url)

                if parsed_link.netloc.lower() != domain:
                    continue

                anchor_text = a_tag.get_text(strip=True).lower()
                target_norm = normalize_url(full_url)
                page_links.append((target_norm, anchor_text, True))
                linked_to.add(target_norm)
                total_internal_links += 1

                # Anchor analysis
                if anchor_text:
                    total_anchor_count += 1
                    if anchor_text in _GENERIC_ANCHORS:
                        generic_anchor_count += 1

                # Enqueue
                if target_norm not in visited and current_depth + 1 <= max_depth:
                    page_depth[target_norm] = current_depth + 1
                    queue.append(full_url)

            # Detect non-crawlable navigation elements (buttons, divs, spans with click handlers)
            for el in soup.find_all(["button", "div", "span"], attrs={"onclick": True}):
                non_crawlable_count += 1
                total_nav_elements += 1

            # Count crawlable nav elements too
            total_nav_elements += len(soup.find_all("a", href=True))

            link_graph[norm] = page_links

    # Analysis
    pages_crawled = len(visited)

    # Orphan pages: linked to but not actually crawled (could be out of depth or disallowed)
    orphan_pages = [u for u in linked_to if u not in visited]

    # Pages with no outgoing internal links
    pages_no_outgoing = [
        page for page, links in link_graph.items() if len(links) == 0
    ]
    if pages_no_outgoing:
        issues.append(
            f"{len(pages_no_outgoing)} pages have no outgoing internal links"
        )

    # Generic anchor percentage
    generic_anchor_pct = "0%"
    if total_anchor_count > 0:
        pct = generic_anchor_count / total_anchor_count * 100
        generic_anchor_pct = f"{pct:.0f}%"
        if pct > 20:
            issues.append(
                f"{pct:.0f}% of anchors are generic (click here, read more, etc.). "
                "Use descriptive anchor text."
            )

    # Non-crawlable nav percentage
    non_crawlable_nav_pct = "0%"
    if total_nav_elements > 0:
        pct = non_crawlable_count / total_nav_elements * 100
        non_crawlable_nav_pct = f"{pct:.0f}%"
        if pct > 10:
            issues.append(
                f"{pct:.0f}% of navigation uses non-crawlable elements (onclick handlers). "
                "Replace with <a href> links."
            )

    # Deepest page
    deepest_page = {"url": start_url, "depth": 0}
    for page, depth in page_depth.items():
        if depth > deepest_page["depth"]:
            deepest_page = {"url": page, "depth": depth}
    if deepest_page["depth"] > 3:
        issues.append(
            f"Deepest page {deepest_page['url']} is {deepest_page['depth']} clicks from start. "
            "Keep important pages within 3 clicks."
        )

    # Average internal links per page
    avg_links = 0.0
    if link_graph:
        avg_links = sum(len(v) for v in link_graph.values()) / len(link_graph)

    if orphan_pages:
        issues.append(f"{len(orphan_pages)} orphan pages found (linked to but not crawled)")

    return {
        "start_url": start_url,
        "pages_crawled": pages_crawled,
        "total_links_found": total_internal_links,
        "orphan_pages": orphan_pages[:50],
        "generic_anchor_pct": generic_anchor_pct,
        "non_crawlable_nav_pct": non_crawlable_nav_pct,
        "deepest_page": deepest_page,
        "avg_links_per_page": round(avg_links, 1),
        "issues": issues,
    }
