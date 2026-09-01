"""Verify LLM-proposed clusters against what Google actually returns.

Thematic clustering asks "do these keywords sound like one topic". That is not
the question SEO turns on. The question is whether Google returns the SAME
RESULTS for them — if it does, one page can rank for both; if it does not, they
need separate pages however similar the words look.

"ai product manager course" and "ai product manager certification" read as one
theme to a language model. If their SERPs are disjoint — course platforms
versus credential bodies — merging them produces one page that ranks for
neither.

So: keep the cheap LLM pass to propose themes, then spend SERP calls ONLY where
the answer could change a decision — on pairs of clusters that look close
enough to be candidates for merging. Clusters that nothing else resembles are
never verified, because confirming them costs money and changes nothing.
"""
from __future__ import annotations

from urllib.parse import urlparse

from . import dataforseo as dfs
from .cache import get_cached, set_cached

# Two keywords are treated as one intent when their top-10 results overlap this
# much. Three shared results out of ten is the common industry rule of thumb;
# expressed as a ratio it is 0.3.
MERGE_THRESHOLD = 0.3
# How many results to compare. Beyond ten, positions carry little intent signal.
DEPTH = 10
# A pair is only worth verifying if the head terms already share vocabulary —
# unrelated clusters do not need a paid call to stay separate.
CANDIDATE_WORD_OVERLAP = 0.3
# Default SERP calls per run. The evaluation needed SERPs for 11 head terms
# across 21 candidate pairs and ran out at 8, leaving one pair unverified (and
# so defaulted to separate). Twelve covers a 13-cluster run with room to spare.
MAX_SERP_CALLS = 12


def _bare(url: str) -> str:
    """Compare on URL without protocol/query — the page, not the link."""
    try:
        parsed = urlparse(url if "//" in url else f"//{url}")
        host = (parsed.netloc or "").lower().removeprefix("www.")
        return f"{host}{parsed.path.rstrip('/')}".lower()
    except Exception:
        return (url or "").lower()


def top_urls(keyword: str, location_code: int, language_code: str) -> list[str]:
    """The top organic results for a keyword, cached across a run."""
    params = {"keyword": keyword, "location_code": location_code,
              "language_code": language_code, "depth": DEPTH}
    cached = get_cached("serp_verify", params)
    if cached is not None:
        return cached
    try:
        rows = dfs.serp_organic(keyword, location_code=location_code,
                               language_code=language_code, depth=DEPTH)
    except Exception as exc:
        print(f"  [serp_verify] SERP failed for {keyword!r}: {exc}")
        return []
    urls = []
    for row in rows or []:
        url = row.get("url") or row.get("link") or ""
        if url:
            urls.append(_bare(url))
    set_cached("serp_verify", params, urls)
    return urls


def overlap(a: list[str], b: list[str]) -> float:
    """Shared results as a share of the smaller set. 0.0 when either is empty."""
    if not a or not b:
        return 0.0
    shared = len(set(a) & set(b))
    return round(shared / min(len(a), len(b)), 2)


def _words(text: str) -> set[str]:
    return {w for w in (text or "").lower().split() if len(w) > 2}


def _candidate_pairs(heads: list[str]) -> list[tuple[int, int]]:
    """Cluster pairs close enough that a SERP check could change the answer."""
    pairs = []
    for i in range(len(heads)):
        for j in range(i + 1, len(heads)):
            wi, wj = _words(heads[i]), _words(heads[j])
            if not wi or not wj:
                continue
            shared = len(wi & wj) / min(len(wi), len(wj))
            if shared >= CANDIDATE_WORD_OVERLAP:
                pairs.append((i, j))
    return pairs


def verify_clusters(
    clusters: list[dict],
    location_code: int,
    language_code: str,
    max_calls: int = MAX_SERP_CALLS,
) -> dict:
    """Check which proposed clusters Google actually treats as the same thing.

    Returns the merge recommendations with their evidence. It does NOT mutate
    the clusters — the pipeline decides what to do, and the numbers are
    published so a reader can disagree.
    """
    heads = [
        (c.get("head_term") or c.get("cluster_name") or c.get("name") or "").strip()
        for c in clusters
    ]
    pairs = _candidate_pairs(heads)
    if not pairs:
        return {
            "checked": 0, "merges": [], "kept_separate": [],
            "note": "No two clusters shared enough vocabulary to be merge "
                    "candidates, so no SERP calls were made.",
        }

    # Only fetch SERPs for head terms that appear in a candidate pair, and stop
    # at the budget — an unverified pair stays separate, which is the safe
    # default (two pages instead of one wrongly merged).
    needed: list[int] = []
    for i, j in pairs:
        for idx in (i, j):
            if idx not in needed:
                needed.append(idx)

    serps: dict[int, list[str]] = {}
    calls = 0
    for idx in needed:
        if calls >= max_calls or dfs.budget_remaining() <= 0:
            break
        if not heads[idx]:
            continue
        serps[idx] = top_urls(heads[idx], location_code, language_code)
        calls += 1

    merges, separate = [], []
    for i, j in pairs:
        if i not in serps or j not in serps:
            separate.append({
                "a": heads[i], "b": heads[j], "overlap": None,
                "why": "not verified (budget) — kept separate, which is the safe default",
            })
            continue
        score = overlap(serps[i], serps[j])
        shared = sorted(set(serps[i]) & set(serps[j]))[:5]
        if score >= MERGE_THRESHOLD:
            merges.append({
                "a": heads[i], "b": heads[j], "a_index": i, "b_index": j,
                "overlap": score, "shared_results": shared,
                "why": f"Google returns {int(score * 100)}% of the same results "
                       f"for both, so one page can serve them",
            })
        else:
            separate.append({
                "a": heads[i], "b": heads[j], "overlap": score,
                "why": f"only {int(score * 100)}% of results are shared — "
                       f"different intent, so they need separate pages",
            })

    return {
        "checked": calls,
        "pairs_considered": len(pairs),
        "merges": merges,
        "kept_separate": separate,
        "threshold": MERGE_THRESHOLD,
        "method": (
            "Clusters were proposed thematically, then head terms of pairs "
            "sharing vocabulary were compared on their live top-10 results. "
            f"Overlap at or above {MERGE_THRESHOLD} means Google treats them as "
            "one intent. Unverified pairs stay separate."
        ),
    }


def apply_merges(clusters: list[dict], verification: dict) -> list[dict]:
    """Fold merged clusters together, recording what was merged and why."""
    merges = verification.get("merges") or []
    if not merges:
        return clusters

    # Union-find over cluster indices, so a chain of merges collapses correctly.
    parent = list(range(len(clusters)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in merges:
        a, b = find(m["a_index"]), find(m["b_index"])
        if a != b:
            parent[max(a, b)] = min(a, b)

    grouped: dict[int, list[int]] = {}
    for idx in range(len(clusters)):
        grouped.setdefault(find(idx), []).append(idx)

    out = []
    for root, members in grouped.items():
        base = dict(clusters[root])
        if len(members) == 1:
            out.append(base)
            continue
        keywords, names = [], []
        for idx in members:
            names.append(clusters[idx].get("cluster_name") or clusters[idx].get("name") or "")
            for kw in clusters[idx].get("keywords") or []:
                name = kw.get("keyword") if isinstance(kw, dict) else kw
                if name and name not in keywords:
                    keywords.append(name)
        base["keywords"] = keywords
        base["merged_from"] = [n for n in names if n]
        base["merge_reason"] = next(
            (m["why"] for m in merges
             if find(m["a_index"]) == root or find(m["b_index"]) == root),
            "SERP overlap",
        )
        out.append(base)
    return out
