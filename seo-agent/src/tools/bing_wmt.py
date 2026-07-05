from __future__ import annotations

import httpx

from ..config import settings


_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


def _headers() -> dict:
    return {"Ocp-Apim-Subscription-Key": settings.bing_wmt_api_key}


def get_site_keywords(site_url: str, count: int = 50) -> dict:
    """Get top keywords for a site from Bing Webmaster Tools."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE}/GetPageQuerystats",
                params={"siteUrl": site_url, "count": count, "page": 0},
                headers=_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("d", [])
                keywords = [
                    {
                        "query": item.get("Query", ""),
                        "clicks": item.get("Clicks", 0),
                        "impressions": item.get("Impressions", 0),
                        "avg_position": item.get("AvgPosition", 0),
                        "date": item.get("Date", ""),
                    }
                    for item in items
                ]
                return {"status": "success", "keywords": keywords, "count": len(keywords)}
            return {"status": "error", "http_status": resp.status_code, "response": resp.text[:500]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_site_stats(site_url: str) -> dict:
    """Get overall site statistics from Bing Webmaster Tools."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE}/GetStats",
                params={"siteUrl": site_url},
                headers=_headers(),
            )
            if resp.status_code == 200:
                return {"status": "success", "data": resp.json().get("d", [])}
            return {"status": "error", "http_status": resp.status_code, "response": resp.text[:500]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def submit_url(site_url: str, page_url: str) -> dict:
    """Submit a URL to Bing for indexing."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{_BASE}/SubmitUrl",
                params={"siteUrl": site_url},
                json={"siteUrl": site_url, "url": page_url},
                headers={**_headers(), "Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return {"status": "success", "message": f"Submitted {page_url}"}
            return {"status": "error", "http_status": resp.status_code, "response": resp.text[:500]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_submitted_urls(site_url: str) -> dict:
    """Get list of submitted URLs and their status."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE}/GetUrlSubmissionStatus",
                params={"siteUrl": site_url},
                headers=_headers(),
            )
            if resp.status_code == 200:
                return {"status": "success", "submissions": resp.json().get("d", [])}
            return {"status": "error", "http_status": resp.status_code, "response": resp.text[:500]}
    except Exception as e:
        return {"status": "error", "message": str(e)}
