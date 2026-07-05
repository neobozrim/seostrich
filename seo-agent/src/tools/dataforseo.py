from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

from ..config import settings


def _auth_header() -> str:
    creds = f"{settings.dataforseo_login}:{settings.dataforseo_password}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


async def _post(endpoint: str, payload: list[dict] | dict) -> dict:
    url = f"{settings.dataforseo_base_url}{endpoint}"
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status_code") and data["status_code"] != 20000:
        raise RuntimeError(
            f"DFS error {endpoint}: status={data.get('status_code')} "
            f"message={data.get('status_message')}"
        )
    return data


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


def keywords_for_site(url: str, limit: int = 100) -> list[dict]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/ranked_keywords/live", [
            {
                "target": _normalize(url),
                "limit": limit,
                "order_by": ["estimated_traffic.desc"],
                "filters": [
                    "impressions_info.impression_info.position,less_than,100"
                ],
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        results = []
        for item in items:
            kw = item.get("keyword_data", {})
            info = item.get("impressions_info", {})
            results.append({
                "keyword": kw.get("keyword", ""),
                "volume": kw.get("search_volume", 0),
                "difficulty": kw.get("keyword_difficulty", 0),
                "cpc": kw.get("cpc", 0),
                "intent": _intent_for(kw.get("keyword", "")),
                "rank": info.get("position", 99),
                "ranking_url": info.get("url", ""),
                "estimated_traffic": info.get("count", 0),
            })
        return results
    return _run(_inner())


def keyword_overview(keywords: list[str], location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/keyword_overview/live", [
            {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        results = []
        for item in items:
            info = item.get("keyword_info", {})
            results.append({
                "keyword": item.get("keyword", ""),
                "volume": info.get("search_volume", 0),
                "difficulty": info.get("keyword_difficulty", 0),
                "cpc": info.get("cpc", 0),
                "competition": info.get("competition", 0),
                "intent": info.get("search_intent", _intent_for(item.get("keyword", ""))),
            })
        return results
    return _run(_inner())


def related_keywords(seed: str, limit: int = 50, location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/related_keywords/live", [
            {
                "keyword": seed,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "order_by": ["search_volume.desc"],
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        return [_kw_item(i) for i in items]
    return _run(_inner())


def keyword_suggestions(seed: str, limit: int = 50, location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/keywords_data/keywords_for_keywords/live", [
            {
                "keywords": [seed],
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "order_by": ["search_volume.desc"],
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        return [_kw_item(i) for i in items]
    return _run(_inner())


def serp_organic(keyword: str, location_code: int = 2840, language_code: str = "en", depth: int = 10) -> list[dict]:
    async def _inner():
        data = await _post("/v3/serp/google/organic/live/advanced", [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "depth": depth,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        results = []
        for item in items:
            if item.get("type") == "organic":
                results.append({
                    "rank": item.get("rank_absolute", 0),
                    "domain": item.get("domain", ""),
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                })
        return results
    return _run(_inner())


def serp_ai_mode(keyword: str, location_code: int = 2840, language_code: str = "en") -> dict:
    async def _inner():
        data = await _post("/v3/serp/google/ai_mode/live/advanced", [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
            }
        ])
        tasks = data.get("tasks", [{}])
        results = tasks[0].get("result", [{}])
        items = results[0].get("items", []) if results else []
        cited = []
        for item in items:
            if item.get("type") == "ai_mode" and item.get("references"):
                for ref in item["references"]:
                    cited.append({
                        "domain": ref.get("domain", ""),
                        "url": ref.get("url", ""),
                        "title": ref.get("title", ""),
                    })
        return {"has_ai_overview": len(items) > 0, "cited_urls": cited}
    return _run(_inner())


def keyword_difficulty(keywords: list[str], location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/keyword_difficulty/live", [
            {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        return [
            {"keyword": i.get("keyword", ""), "difficulty": i.get("keyword_difficulty", 0)}
            for i in items
        ]
    return _run(_inner())


def historical_search_volume(keywords: list[str], location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/keywords_data/historical_search_volume/live", [
            {
                "keywords": keywords[:700],
                "location_code": location_code,
                "language_code": language_code,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        results = []
        for item in items:
            monthly = item.get("monthly_searches", [])
            volumes = [m.get("search_volume", 0) for m in monthly[-12:]] if monthly else []
            results.append({
                "keyword": item.get("keyword", ""),
                "volumes": volumes,
                "avg_volume": sum(volumes) / max(len(volumes), 1),
            })
        return results
    return _run(_inner())


def trends_trending(location_code: int = 2840, language_code: str = "en", limit: int = 25) -> list[dict]:
    async def _inner():
        data = await _post("/v3/keywords_data/trends/trending_keywords/live", [
            {
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        return [
            {"keyword": i.get("keyword", ""), "volume": i.get("search_volume", 0)}
            for i in items
        ]
    return _run(_inner())


def competitors_domain(domain: str, limit: int = 10) -> list[str]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/competitors_domain/live", [
            {
                "target": _normalize(domain),
                "limit": limit,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        return [i.get("domain", "") for i in items]
    return _run(_inner())


def domain_intersection(domain1: str, domain2: str, limit: int = 50) -> list[dict]:
    async def _inner():
        data = await _post("/v3/dataforseo_labs/domain_intersection/live", [
            {
                "target": _normalize(domain1),
                "competitor": _normalize(domain2),
                "limit": limit,
            }
        ])
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        results = []
        for item in items:
            kw_data = item.get("keyword_data", {})
            results.append({
                "keyword": kw_data.get("keyword", ""),
                "volume": kw_data.get("search_volume", 0),
                "difficulty": kw_data.get("keyword_difficulty", 0),
                "intent": _intent_for(kw_data.get("keyword", "")),
            })
        return results
    return _run(_inner())


def _normalize(url: str) -> str:
    url = url.strip()
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.rstrip("/")


def _kw_item(i: dict) -> dict:
    info = i.get("keyword_info", i)
    return {
        "keyword": i.get("keyword", ""),
        "volume": info.get("search_volume", 0),
        "difficulty": info.get("keyword_difficulty", 0),
        "cpc": info.get("cpc", 0),
        "intent": info.get("search_intent", _intent_for(i.get("keyword", ""))),
    }


_INTENT_PATTERNS = {
    "transactional": ["buy", "price", "discount", "deal", "coupon", "order", "cheap"],
    "commercial": ["best", "top", "review", "compare", "vs", "alternative", "tool", "software", "platform"],
    "navigational": ["login", "signin", "website", "app", "dashboard"],
}


def _intent_for(keyword: str) -> str:
    kw_lower = keyword.lower()
    for intent, patterns in _INTENT_PATTERNS.items():
        if any(p in kw_lower for p in patterns):
            return intent
    return "informational"
