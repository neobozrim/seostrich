from __future__ import annotations

from . import dataforseo as dfs
from .cache import get_cached, set_cached


def pull_universe(
    seeds: dict,
    location_code: int = 2840,
    language_code: str = "en",
    competitor_urls: list[str] = None,
) -> dict:
    """Expand keyword seeds into full keyword universe using DataForSEO."""
    all_keywords = []

    # Expand each seed category
    for seed_list in [
        seeds.get("business_seeds", []),
        seeds.get("site_seeds", []),
        seeds.get("competitor_seeds", []),
    ]:
        for seed in seed_list:
            # Check cache for related keywords
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
                all_keywords.extend(related)

            # Check cache for keyword suggestions
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
                all_keywords.extend(suggestions)

    # Check cache for trending keywords (optional, skip on error)
    try:
        params = {"location_code": location_code, "language_code": language_code}
        cached = get_cached("trends_trending", params)
        if cached:
            trends = cached
        else:
            trends = dfs.trends_trending(location_code=location_code, language_code=language_code, limit=25)
            set_cached("trends_trending", params, trends)
        if trends:
            all_keywords.extend(trends)
    except Exception as e:
        print(f"  [WARN] trends_trending failed (non-fatal): {e}")

    # Get competitor keyword gaps
    if competitor_urls:
        for comp_url in competitor_urls[:3]:
            try:
                pass
            except Exception:
                pass

    # Deduplicate and filter
    seen = set()
    unique_keywords = []
    for kw in all_keywords:
        key = kw.get("keyword", "").lower()
        if key and key not in seen:
            seen.add(key)
            unique_keywords.append(kw)

    # Sort by volume (handle None values)
    unique_keywords.sort(key=lambda x: x.get("volume") or 0, reverse=True)

    return {
        "keywords": unique_keywords[:200],  # Top 200
        "total_count": len(unique_keywords),
    }
