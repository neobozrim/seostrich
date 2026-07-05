from __future__ import annotations

from . import dataforseo as dfs


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
            # Get related keywords
            related = dfs.related_keywords(seed, limit=50, location_code=location_code, language_code=language_code)
            all_keywords.extend(related)
            
            # Get keyword suggestions
            suggestions = dfs.keyword_suggestions(seed, limit=50, location_code=location_code, language_code=language_code)
            all_keywords.extend(suggestions)
    
    # Get trending keywords
    trends = dfs.trends_trending(location_code=location_code, language_code=language_code, limit=25)
    all_keywords.extend(trends)
    
    # Get competitor keyword gaps
    if competitor_urls:
        for comp_url in competitor_urls[:3]:
            try:
                # Get domain intersection (what we both rank for)
                # This requires knowing our domain, skip for now
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
    
    # Sort by volume
    unique_keywords.sort(key=lambda x: x.get("volume", 0), reverse=True)
    
    return {
        "keywords": unique_keywords[:200],  # Top 200
        "total_count": len(unique_keywords),
    }
