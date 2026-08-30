from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


def _extract_text(html: str) -> str:
    """Strip HTML and normalize whitespace to plain text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style content
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _word_tokens(text: str) -> set[str]:
    """Tokenize text into lowercase word set."""
    return set(re.findall(r"\b\w+\b", text.lower()))


def _shingles(text: str, n: int = 3) -> set[str]:
    """Create character n-gram shingles from text."""
    words = text.lower().split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _jaccard(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def duplicate_content_scan(
    urls: list[str], similarity_threshold: float = 0.85
) -> dict:
    """Scan URLs for duplicate or near-duplicate content using shingling."""
    if not urls:
        return {
            "urls_scanned": 0,
            "duplicate_groups": [],
            "unique_pages": 0,
            "near_duplicate_pages": 0,
        }

    normalized: list[str] = []
    for u in urls:
        if not u.startswith("http"):
            u = f"https://{u}"
        normalized.append(u)

    # Fetch and extract text
    page_texts: list[tuple[str, str]] = []  # (url, text)
    with httpx.Client(
        timeout=30, follow_redirects=True, headers={"User-Agent": "SEOAgent/1.0"}
    ) as client:
        for url in normalized:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    text = _extract_text(resp.text[:200_000])
                    page_texts.append((url, text))
                else:
                    page_texts.append((url, ""))
            except Exception:
                page_texts.append((url, ""))

    # Compute shingles for each page
    page_shingles: list[tuple[str, set[str], int]] = []  # (url, shingles, text_length)
    for url, text in page_texts:
        shingles = _shingles(text, n=3)
        page_shingles.append((url, shingles, len(text)))

    # Pairwise comparison
    n = len(page_shingles)
    similarity_matrix: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim = _jaccard(page_shingles[i][1], page_shingles[j][1])
            if sim >= similarity_threshold:
                similarity_matrix[(i, j)] = sim

    # Group into clusters using union-find approach
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j in similarity_matrix:
        union(i, j)

    # Build clusters
    clusters: dict[int, list[int]] = {}
    for idx in range(n):
        root = find(idx)
        clusters.setdefault(root, []).append(idx)

    duplicate_groups: list[dict] = []
    near_dup_count = 0
    for root, members in clusters.items():
        if len(members) < 2:
            continue
        # Find max similarity in cluster
        max_sim = 0.0
        for i in members:
            for j in members:
                key = (min(i, j), max(i, j))
                if key in similarity_matrix:
                    max_sim = max(max_sim, similarity_matrix[key])

        # Recommend canonical: longest content
        best_idx = max(members, key=lambda m: page_shingles[m][2])
        canonical_url = page_shingles[best_idx][0]

        cluster_urls = [page_shingles[m][0] for m in members]
        duplicate_groups.append({
            "urls": cluster_urls,
            "similarity": round(max_sim, 3),
            "canonical_recommendation": canonical_url,
        })
        near_dup_count += len(members)

    return {
        "urls_scanned": len(normalized),
        "duplicate_groups": duplicate_groups,
        "unique_pages": len(normalized) - near_dup_count,
        "near_duplicate_pages": near_dup_count,
    }
