from __future__ import annotations

from urllib.parse import urlparse

from . import dataforseo as dfs
from .cache import get_cached, set_cached

# Below this many deduped keywords the market is "thin" and we escalate to
# competitor discovery so the strategy graph still has material to work with.
THIN_THRESHOLD = 15
# Cap direct seed expansion to keep the DataForSEO budget sane on wide briefs.
MAX_EXPAND_SEEDS = 5


def pull_universe(
    seeds: dict,
    location_code: int = 2840,
    language_code: str = "en",
    competitor_urls: list[str] = None,
) -> dict:
    """Expand keyword seeds into a full keyword universe using DataForSEO.

    Thin-market resilience: some languages/niches have few or no related
    keywords (e.g. "изречена поезия" in Bulgarian). When direct expansion
    comes back thin we fall back to what competitors rank for, and we always
    keep the seeds themselves in the universe so the strategy graph never
    runs dry.
    """
    competitor_urls = competitor_urls or []
    all_keywords: list[dict] = []

    # ---- Ladder 1: direct seed expansion (related + suggestions) ----
    expand_seeds = _collect_seeds(seeds)[:MAX_EXPAND_SEEDS]
    for seed in expand_seeds:
        all_keywords.extend(_expand_seed(seed, location_code, language_code))

    # ---- Ladder 2: trending keywords ----
    # Disabled: the DFS trending_keywords endpoint 404s (does not exist), so the
    # call only ever burned budget. Re-enable once a working endpoint is wired.
    # all_keywords.extend(_trending(location_code, language_code))

    # Always keep the seeds themselves as a floor. In thin markets these are
    # often the only usable terms — the discovery-input keyword survives even
    # when the APIs return nothing for it.
    all_keywords.extend(_seeds_as_keywords(seeds))

    unique = _dedupe(all_keywords)

    # ---- Ladder 3: thin market -> competitor discovery ----
    if len(unique) < THIN_THRESHOLD and dfs.budget_remaining() > 0:
        print(f"  [pull_universe] thin market ({len(unique)} keywords) -> competitor discovery")
        comp_keywords = _competitor_keywords(
            expand_seeds, competitor_urls, location_code, language_code
        )
        all_keywords.extend(comp_keywords)
        unique = _dedupe(all_keywords)

    # Sort by volume (handle None values); seeds/competitor rows with no
    # volume sink to the bottom in rich markets but carry thin ones.
    unique.sort(key=lambda x: x.get("volume") or 0, reverse=True)

    return {
        "keywords": unique[:200],  # Top 200
        "total_count": len(unique),
    }


def _collect_seeds(seeds: dict) -> list[str]:
    """Flatten seed categories into an ordered, de-duplicated seed list."""
    ordered: list[str] = []
    seen = set()
    for seed_list in [
        seeds.get("business_seeds", []),
        seeds.get("site_seeds", []),
        seeds.get("competitor_seeds", []),
    ]:
        for seed in seed_list or []:
            key = (seed or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append(seed.strip())
    return ordered


def _expand_seed(seed: str, location_code: int, language_code: str) -> list[dict]:
    """Related keywords + suggestions for one seed, cache-backed."""
    results: list[dict] = []
    params = {"seed": seed, "location_code": location_code, "language_code": language_code}

    cached = get_cached("related_keywords", params)
    if cached:
        related = cached
    else:
        try:
            related = dfs.related_keywords(seed, limit=50, location_code=location_code, language_code=language_code)
            set_cached("related_keywords", params, related)
        except Exception as e:
            print(f"  [WARN] related_keywords failed for '{seed}': {e}")
            related = []
    if related:
        results.extend(related)

    cached = get_cached("keyword_suggestions", params)
    if cached:
        suggestions = cached
    else:
        try:
            suggestions = dfs.keyword_suggestions(seed, limit=50, location_code=location_code, language_code=language_code)
            set_cached("keyword_suggestions", params, suggestions)
        except Exception as e:
            print(f"  [WARN] keyword_suggestions failed for '{seed}': {e}")
            suggestions = []
    if suggestions:
        results.extend(suggestions)

    return results


def _trending(location_code: int, language_code: str) -> list[dict]:
    params = {"location_code": location_code, "language_code": language_code}
    try:
        cached = get_cached("trends_trending", params)
        if cached:
            trends = cached
        else:
            trends = dfs.trends_trending(location_code=location_code, language_code=language_code, limit=25)
            set_cached("trends_trending", params, trends)
        return trends or []
    except Exception as e:
        print(f"  [WARN] trends_trending failed (non-fatal): {e}")
        return []


def _seeds_as_keywords(seeds: dict) -> list[dict]:
    """The seeds themselves as low-confidence keyword rows (volume unknown)."""
    rows: list[dict] = []
    for seed in _collect_seeds(seeds):
        rows.append({
            "keyword": seed,
            "volume": 0,
            "difficulty": 0,
            "cpc": 0,
            "intent": "informational",
            "source": "seed",
        })
    return rows


def _competitor_keywords(
    seeds: list[str],
    competitor_urls: list[str],
    location_code: int,
    language_code: str,
) -> list[dict]:
    """What competitors rank for — the primary fallback for thin markets.

    Uses explicit competitor URLs when given; otherwise discovers the domains
    that rank for our seeds via organic SERP, then pulls their ranked keywords.
    """
    domains: list[str] = []
    seen_domains = set()

    def _add(domain: str) -> None:
        d = (domain or "").lower().strip()
        d = d.removeprefix("www.")
        if d and d not in seen_domains:
            seen_domains.add(d)
            domains.append(d)

    # Explicit competitor URLs first.
    for url in competitor_urls[:3]:
        _add(_domain_of(url))

    # Otherwise discover who ranks for our seeds.
    if not domains and seeds:
        for seed in seeds[:2]:
            try:
                serp = dfs.serp_organic(
                    seed, location_code=location_code,
                    language_code=language_code, depth=10,
                )
            except Exception as e:
                print(f"  [WARN] serp_organic failed for '{seed}': {e}")
                continue
            for row in serp:
                _add(row.get("domain", ""))
            if len(domains) >= 2:
                break

    results: list[dict] = []
    for domain in domains[:2]:
        try:
            kws = dfs.keywords_for_site(domain, limit=50)
        except Exception as e:
            print(f"  [WARN] keywords_for_site failed for '{domain}': {e}")
            continue
        if kws:
            print(f"  [pull_universe] competitor '{domain}' contributed {len(kws)} keywords")
            results.extend(kws)
    return results


def _domain_of(url: str) -> str:
    if not url:
        return ""
    value = url if "://" in url else f"https://{url}"
    try:
        return urlparse(value).netloc
    except Exception:
        return ""


def _dedupe(all_keywords: list[dict]) -> list[dict]:
    seen = set()
    unique: list[dict] = []
    for kw in all_keywords:
        key = (kw.get("keyword") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(kw)
    return unique
