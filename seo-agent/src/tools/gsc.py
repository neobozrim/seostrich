"""Google Search Console API tool.

Uses service account credentials to authenticate with the Search Console API.
Provides performance data, sitemap management, and URL inspection.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

_SCOPES = ["https://www.googleapis.com/auth/webmasters"]
_BASE = "https://www.googleapis.com/webmasters/v3"
_SEARCH_ANALYTICS = "https://searchconsole.googleapis.com/v1"


def _get_credentials():
    """Load and return Google service account credentials."""
    creds_path = Path(settings.gsc_credentials_path)

    if not creds_path.is_absolute():
        # Resolve relative to project root (seo-agent/)
        project_root = Path(__file__).resolve().parent.parent.parent
        creds_path = project_root / creds_path

    if not creds_path.exists():
        raise FileNotFoundError(f"GSC credentials not found at {creds_path}")

    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=_SCOPES
    )


def _request(method: str, url: str, **kwargs) -> dict:
    """Make an authenticated request to the GSC API."""
    creds = _get_credentials()

    import google.auth.transport.requests
    creds.refresh(google.auth.transport.requests.Request())

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {creds.token}"
    headers["Content-Type"] = "application/json"

    with httpx.Client(timeout=30) as client:
        resp = client.request(method, url, headers=headers, **kwargs)

    if resp.status_code >= 400:
        return {
            "status": "error",
            "http_status": resp.status_code,
            "response": resp.text[:500],
        }

    if resp.status_code == 204 or not resp.text:
        return {"status": "success"}

    return {"status": "success", "data": resp.json()}


def gsc_performance(
    site_url: str,
    days: int = 28,
    dimensions: list[str] | None = None,
) -> dict:
    """Get search performance data (clicks, impressions, CTR, position).

    Args:
        site_url: The site URL as registered in GSC (e.g. "https://productpirates.club")
        days: Number of days to look back (max ~90 days, data has 2-day delay)
        dimensions: Grouping dimensions. Options: "query", "page", "date", "device", "country"
    """
    if dimensions is None:
        dimensions = ["query"]

    end_date = datetime.now() - timedelta(days=3)  # GSC data has ~2 day delay
    start_date = end_date - timedelta(days=days)

    payload = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "dimensions": dimensions,
        "rowLimit": 25,
    }

    url = f"{_SEARCH_ANALYTICS}/sites/{_encode_url(_normalize_site_url(site_url))}/searchAnalytics/query"
    result = _request("POST", url, json=payload)

    if result.get("status") != "success":
        return result

    rows = result.get("data", {}).get("rows", [])
    formatted = []
    for row in rows:
        entry = {
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "position": round(row.get("position", 0), 1),
        }
        keys = row.get("keys", [])
        for i, dim in enumerate(dimensions):
            if i < len(keys):
                entry[dim] = keys[i]
        formatted.append(entry)

    return {
        "status": "success",
        "site_url": site_url,
        "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        "dimensions": dimensions,
        "rows": formatted,
        "total_rows": len(formatted),
    }


def gsc_submit_sitemap(site_url: str, sitemap_url: str) -> dict:
    """Submit a sitemap to Google Search Console.

    Args:
        site_url: The site URL as registered in GSC
        sitemap_url: The full URL of the sitemap to submit
    """
    url = f"{_BASE}/sites/{_encode_url(_normalize_site_url(site_url))}/sitemaps/{_encode_url(sitemap_url)}"
    return _request("PUT", url)


def gsc_list_sitemaps(site_url: str) -> dict:
    """List all sitemaps submitted to Google Search Console.

    Args:
        site_url: The site URL as registered in GSC
    """
    url = f"{_BASE}/sites/{_encode_url(_normalize_site_url(site_url))}/sitemaps"
    result = _request("GET", url)

    if result.get("status") != "success":
        return result

    sitemaps = result.get("data", {}).get("sitemap", [])
    formatted = [
        {
            "path": s.get("path", ""),
            "last_submitted": s.get("lastSubmitted", ""),
            "warnings": s.get("warnings", 0),
            "errors": s.get("errors", 0),
            "contents": s.get("contents", []),
        }
        for s in sitemaps
    ]

    return {
        "status": "success",
        "site_url": site_url,
        "sitemaps": formatted,
        "count": len(formatted),
    }


def gsc_inspect_url(site_url: str, inspection_url: str) -> dict:
    """Inspect a URL's indexing status in Google Search Console.

    Args:
        site_url: The site URL as registered in GSC
        inspection_url: The specific URL to inspect
    """
    url = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
    payload = {
        "inspectionUrl": inspection_url,
        "siteUrl": _normalize_site_url(site_url),
    }

    result = _request("POST", url, json=payload)

    if result.get("status") != "success":
        return result

    inspection = result.get("data", {}).get("inspectionResult", {}).get("indexStatusResult", {})
    verdict = inspection.get("verdict", "UNKNOWN")
    coverage = inspection.get("coverageState", "UNKNOWN")

    return {
        "status": "success",
        "url": inspection_url,
        "verdict": verdict,
        "coverage_state": coverage,
        "last_crawl": inspection.get("lastCrawlTime", ""),
        "page_fetch": inspection.get("pageFetchState", ""),
        "indexing_state": inspection.get("indexingState", ""),
        "robots_txt_state": inspection.get("robotsTxtState", ""),
        "mobile_usability": result.get("data", {}).get("inspectionResult", {}).get("mobileUsabilityResult", {}).get("verdict", "UNKNOWN"),
    }


def gsc_list_sites() -> dict:
    """List all sites in the Google Search Console account."""
    url = f"{_BASE}/sites"
    result = _request("GET", url)

    if result.get("status") != "success":
        return result

    sites = result.get("data", {}).get("siteEntry", [])
    formatted = [
        {
            "url": s.get("siteUrl", ""),
            "permission": s.get("permissionLevel", ""),
        }
        for s in sites
    ]

    return {
        "status": "success",
        "sites": formatted,
        "count": len(formatted),
    }


def _encode_url(url: str) -> str:
    """URL-encode a site/sitemap URL for use in API path.

    Handles both URL-prefix properties (https://example.com) and
    domain properties (sc-domain:example.com).
    """
    from urllib.parse import quote
    if url.startswith("sc-domain:"):
        return quote(url, safe=":")
    return quote(url, safe="")


def _normalize_site_url(site_url: str) -> str:
    """Normalize a site URL to GSC format.

    If given 'productpirates.club' or 'https://productpirates.club',
    tries 'sc-domain:productpirates.club' first (domain properties).
    """
    site_url = site_url.strip()
    if site_url.startswith("sc-domain:"):
        return site_url
    # Strip protocol for domain property format
    clean = site_url
    for prefix in ("https://", "http://", "www."):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    clean = clean.rstrip("/")
    return f"sc-domain:{clean}"
