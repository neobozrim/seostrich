"""Result caching for expensive API calls."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

CACHE_DIR = Path(os.getenv("CACHE_DIR", "cache"))
CACHE_TTL_HOURS = 24 * 7  # 1 week default


def normalize_domain(domain: str) -> str:
    """Normalize domain for consistent caching.
    
    Examples:
        https://productpirates.club -> productpirates.club
        www.productpirates.club -> productpirates.club
        productpirates.club/ -> productpirates.club
    """
    # Remove protocol
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    
    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Remove trailing slash and path
    domain = domain.split("/")[0]
    
    return domain.lower()


def get_cache_path(tool_name: str, params: dict) -> Path:
    """Generate cache file path from tool name and parameters."""
    # Create deterministic hash from sorted params
    param_str = json.dumps(params, sort_keys=True)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
    
    return CACHE_DIR / f"{tool_name}_{param_hash}.json"


def get_cached(tool_name: str, params: dict, max_age_hours: int = CACHE_TTL_HOURS) -> dict | None:
    """Get cached result if it exists and is fresh.
    
    Args:
        tool_name: Name of the tool
        params: Tool parameters (will be JSON-serialized for hashing)
        max_age_hours: Maximum age in hours before cache expires
        
    Returns:
        Cached result dict or None if not found/expired
    """
    cache_path = get_cache_path(tool_name, params)
    
    if not cache_path.exists():
        return None
    
    try:
        with open(cache_path) as f:
            cached = json.load(f)
        
        # Check age
        cached_time = datetime.fromisoformat(cached["timestamp"])
        if datetime.now() - cached_time > timedelta(hours=max_age_hours):
            cache_path.unlink()
            return None
        
        return cached["result"]
    except Exception:
        return None


def set_cached(tool_name: str, params: dict, result: dict) -> None:
    """Store result in cache.
    
    Args:
        tool_name: Name of the tool
        params: Tool parameters
        result: Result to cache
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = get_cache_path(tool_name, params)
    
    with open(cache_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "params": params,
            "result": result,
        }, f, indent=2)


def clear_cache(tool_name: str | None = None) -> int:
    """Clear cache entries.
    
    Args:
        tool_name: If provided, only clear this tool's cache. If None, clear all.
        
    Returns:
        Number of cache files deleted
    """
    if not CACHE_DIR.exists():
        return 0
    
    deleted = 0
    for cache_file in CACHE_DIR.glob("*.json"):
        if tool_name is None or cache_file.name.startswith(f"{tool_name}_"):
            cache_file.unlink()
            deleted += 1
    
    return deleted
