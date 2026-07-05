from __future__ import annotations

import httpx


def submit_indexnow(urls: list[str], key: str, key_location: str = "") -> dict:
    """Submit URLs to IndexNow for faster indexing."""
    if not urls:
        return {"status": "error", "message": "No URLs provided"}

    # Determine host from first URL
    from urllib.parse import urlparse
    host = urlparse(urls[0]).netloc

    payload = {
        "host": host,
        "key": key,
        "urlList": urls,
    }
    if key_location:
        payload["keyLocation"] = key_location

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.indexnow.org/indexnow",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            return {
                "status": "success" if resp.status_code in (200, 202) else "error",
                "http_status": resp.status_code,
                "urls_submitted": len(urls),
                "response": resp.text[:500],
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def submit_single_url(url: str, key: str, key_location: str = "") -> dict:
    """Submit a single URL to IndexNow."""
    return submit_indexnow([url], key, key_location)
