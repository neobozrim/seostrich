from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

from ..config import settings


def _auth_header() -> str:
    creds = f"{settings.dataforseo_login}:{settings.dataforseo_password}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


class DFSBudgetExceeded(RuntimeError):
    """The run hit its DataForSEO call cap — stop and ask the user."""


# Per-run call accounting. Keyed by pipeline run id (chat sessions reuse
# their run id across messages, so the cap spans the whole conversation).
_RUN_STATS: dict[str, dict] = {}
_CAP_OVERRIDES: dict[str, int] = {}


def _budget_key() -> str:
    from .. import pipeline_recorder

    return pipeline_recorder.active_run_id() or "_no_run"


def dfs_usage_report(run_id: str | None = None) -> str:
    stats = _RUN_STATS.get(run_id or _budget_key())
    if not stats or not stats["calls"]:
        return "No DataForSEO calls made yet this run"
    parts = ", ".join(f"{n} x{c}" for n, c in sorted(stats["by_endpoint"].items()))
    return f"{stats['calls']} calls so far ({parts})"


def budget_remaining(run_id: str | None = None) -> int:
    """Paid DFS calls still available this run before hitting the cap."""
    key = run_id or _budget_key()
    calls = (_RUN_STATS.get(key) or {}).get("calls", 0)
    cap = _CAP_OVERRIDES.get(key, settings.dfs_max_calls_per_run)
    return max(0, cap - calls)


def _account(endpoint: str) -> None:
    key = _budget_key()
    stats = _RUN_STATS.setdefault(key, {"calls": 0, "by_endpoint": {}})
    cap = _CAP_OVERRIDES.get(key, settings.dfs_max_calls_per_run)
    if stats["calls"] >= cap:
        raise DFSBudgetExceeded(
            f"DataForSEO call budget reached: {dfs_usage_report(key)} against a cap of {cap} per run. "
            "Do NOT retry this call. Report progress to the user and ask whether to continue."
        )
    stats["calls"] += 1
    segments = [s for s in endpoint.strip("/").split("/") if s not in ("v3", "live", "advanced")]
    name = segments[-1] if segments else endpoint
    stats["by_endpoint"][name] = stats["by_endpoint"].get(name, 0) + 1


def continue_dfs_budget(run_id: str, extra: int = 25) -> int | None:
    """Extend the cap after the user approved continuing. Returns the new cap,
    or None when this run never hit its cap."""
    stats = _RUN_STATS.get(run_id)
    cap = _CAP_OVERRIDES.get(run_id, settings.dfs_max_calls_per_run)
    if not stats or stats["calls"] < cap:
        return None
    _CAP_OVERRIDES[run_id] = cap + extra
    return _CAP_OVERRIDES[run_id]


async def _post(endpoint: str, payload: list[dict] | dict) -> dict:
    _account(endpoint)
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


async def _get(endpoint: str) -> dict:
    """GET for reference endpoints (locations/languages) — free, not budgeted."""
    url = f"{settings.dataforseo_base_url}{endpoint}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers={"Authorization": _auth_header()})
        resp.raise_for_status()
        return resp.json()


_LOC_LANG_CACHE: dict[int, list[str]] | None = None


async def _location_languages() -> dict[int, list[str]]:
    """location_code -> supported language codes, most keyword coverage first.

    Cached per process; sourced from DFS's own locations_and_languages so we
    never pay for a call with an unsupported location/language pair.
    """
    global _LOC_LANG_CACHE
    if _LOC_LANG_CACHE is not None:
        return _LOC_LANG_CACHE
    try:
        data = await _get("/v3/dataforseo_labs/locations_and_languages")
    except Exception as exc:
        print(f"  [dfs] locations_and_languages unavailable: {exc}")
        return {}
    tasks = data.get("tasks") or []
    result = (tasks[0] or {}).get("result") if tasks else None
    items = result if isinstance(result, list) else []
    cache: dict[int, list[str]] = {}
    for item in items:
        langs = sorted(
            item.get("available_languages") or [],
            key=lambda l: l.get("keywords", 0),
            reverse=True,
        )
        codes = [l.get("language_code") for l in langs if l.get("language_code")]
        if codes:
            cache[item.get("location_code")] = codes
    if cache:
        _LOC_LANG_CACHE = cache
    return cache


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


# Google market -> language DFS accepts for that location (40501 otherwise).
_LOCATION_LANG = {2100: "bg", 2276: "de", 2250: "fr", 2724: "es", 2380: "it", 2643: "ru"}


def _default_lang(location_code: int) -> str:
    return _LOCATION_LANG.get(location_code, "en")


def _task_status(data: dict):
    tasks = data.get("tasks") or []
    return (tasks[0] or {}).get("status_code") if tasks else data.get("status_code")


def _task_items(data: dict, label: str = "") -> list:
    """Safely extract tasks[0].result[0].items — DFS returns result:null on failed tasks."""
    tasks = data.get("tasks") or []
    if not tasks:
        return []
    task = tasks[0] or {}
    result = task.get("result")
    if not result:
        status = task.get("status_code") or data.get("status_code")
        message = task.get("status_message") or data.get("status_message")
        print(f"  [dfs] empty result{f' for {label}' if label else ''}: status={status} {message}")
        return []
    first = result[0] if isinstance(result, list) else {}
    return (first or {}).get("items") or []


def keywords_for_site(url: str, limit: int = 100) -> list[dict]:
    async def _inner():
        payload = {
            "target": _normalize(url),
            "limit": limit,
        }
        data = await _post("/v3/dataforseo_labs/ranked_keywords/live", [payload])
        items = _task_items(data)
        results = []
        for item in items:
            kw = item.get("keyword_data") or {}
            info = kw.get("keyword_info") or {}
            serp = item.get("ranked_serp_element") or {}
            serp_item = serp.get("serp_item") or {}
            results.append({
                "keyword": kw.get("keyword", ""),
                "volume": info.get("search_volume", 0),
                "difficulty": serp.get("keyword_difficulty", 0),
                "cpc": info.get("cpc", 0),
                "intent": _intent_for(kw.get("keyword", "")),
                "rank": serp_item.get("rank_absolute", 99),
                "ranking_url": serp_item.get("url", ""),
                "estimated_traffic": serp_item.get("etv", 0),
            })
        return results
    return _run(_inner())


def keyword_overview(keywords: list[str], location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        results = []
        # One paid call per keyword — cap the batch to keep runs affordable
        selected = list(keywords)[:20]
        if len(keywords) > 20:
            print(f"[keyword_overview] capping {len(keywords)} keywords to 20 (one paid call each)")
        # Use keyword_suggestions endpoint to get data for specific keywords
        for kw in selected:
            data = await _post("/v3/dataforseo_labs/google/keyword_suggestions/live", [
                {
                    "keyword": kw,
                    "location_code": location_code,
                    "language_code": language_code,
                    "limit": 1,  # Just get the keyword itself
                }
            ])
            items = _task_items(data)
            if items:
                item = items[0]
                info = item.get("keyword_info", {})
                props = item.get("keyword_properties", {})
                intent_info = item.get("search_intent_info", {})
                results.append({
                    "keyword": item.get("keyword", kw),
                    "volume": info.get("search_volume", 0),
                    "difficulty": props.get("keyword_difficulty", 0),
                    "cpc": info.get("cpc", 0),
                    "competition": info.get("competition", 0),
                    "intent": intent_info.get("type", _intent_for(kw)),
                })
        return results
    return _run(_inner())


_LANG_REJECTED: set[tuple[int, str]] = set()


async def _labs_keywords(endpoint: str, seed: str, limit: int, location_code: int, language_code: str) -> dict:
    """Post a labs keyword call with a DFS-supported language for the location.

    The language is resolved up front from locations_and_languages (cached),
    so unsupported pairs never burn a paid call; the 40501 retry is a last resort.
    """
    supported = (await _location_languages()).get(location_code)
    if supported:
        lang = language_code if language_code in supported else supported[0]
    elif (location_code, language_code) in _LANG_REJECTED:
        lang = _default_lang(location_code)
    else:
        lang = language_code
    payload = {
        "keyword": seed,
        "location_code": location_code,
        "language_code": lang,
        "limit": limit,
    }
    data = await _post(endpoint, [payload])
    if _task_status(data) == 40501 and lang != _default_lang(location_code):
        _LANG_REJECTED.add((location_code, language_code))
        payload["language_code"] = _default_lang(location_code)
        print(f"  [dfs] {endpoint.split('/')[-2]}: language '{language_code}' invalid for location {location_code}; retried with '{payload['language_code']}'")
        data = await _post(endpoint, [payload])
    return data


def related_keywords(seed: str, limit: int = 50, location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _labs_keywords("/v3/dataforseo_labs/google/related_keywords/live", seed, limit, location_code, language_code)
        items = _task_items(data)
        return [_kw_item_related(i) for i in items]
    return _run(_inner())


def keyword_suggestions(seed: str, limit: int = 50, location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _labs_keywords("/v3/dataforseo_labs/google/keyword_suggestions/live", seed, limit, location_code, language_code)
        items = _task_items(data)
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
        items = _task_items(data)
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
        items = _task_items(data)
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
    # DFS has no standalone difficulty endpoint — difficulty lives in
    # keyword_suggestions' keyword_properties. One call per keyword, capped.
    async def _inner():
        results = []
        for kw in list(keywords)[:10]:
            data = await _labs_keywords(
                "/v3/dataforseo_labs/google/keyword_suggestions/live",
                kw, 1, location_code, language_code,
            )
            items = _task_items(data)
            if items:
                props = items[0].get("keyword_properties", {})
                results.append({
                    "keyword": items[0].get("keyword", kw),
                    "difficulty": props.get("keyword_difficulty", 0),
                })
        return results
    return _run(_inner())


def historical_search_volume(keywords: list[str], location_code: int = 2840, language_code: str = "en") -> list[dict]:
    async def _inner():
        data = await _post("/v3/keywords_data/historical_search_volume/live", [
            {
                "keywords": keywords[:150],
                "location_code": location_code,
                "language_code": language_code,
            }
        ])
        items = _task_items(data)
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
        items = _task_items(data)
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
        items = _task_items(data)
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
        items = _task_items(data)
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
    """Parse keyword_suggestions response item."""
    info = i.get("keyword_info", {})
    props = i.get("keyword_properties", {})
    intent_info = i.get("search_intent_info", {})
    return {
        "keyword": i.get("keyword", ""),
        "volume": info.get("search_volume", 0),
        "difficulty": props.get("keyword_difficulty", info.get("keyword_difficulty", 0)),
        "cpc": info.get("cpc", 0),
        "intent": intent_info.get("type", _intent_for(i.get("keyword", ""))),
    }


def _kw_item_related(i: dict) -> dict:
    """Parse related_keywords response item (nested under keyword_data)."""
    kd = i.get("keyword_data", {})
    info = kd.get("keyword_info", {})
    props = kd.get("keyword_properties", {})
    intent_info = kd.get("search_intent_info", {})
    return {
        "keyword": kd.get("keyword", ""),
        "volume": info.get("search_volume", 0),
        "difficulty": props.get("keyword_difficulty", info.get("keyword_difficulty", 0)),
        "cpc": info.get("cpc", 0),
        "intent": intent_info.get("type", _intent_for(kd.get("keyword", ""))),
    }


def ai_mentions(domain: str, limit: int = 20) -> list[dict]:
    """Get AI mentions for a domain - tracks how AI systems cite/reference the domain.

    Args:
        domain: Target domain (e.g., "example.com")
        limit: Maximum number of mentions to return

    Returns:
        List of dicts with mention data including source, query, and citation details
    """
    async def _inner():
        data = await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [
            {
                "target": _normalize(domain),
                "limit": limit,
            }
        ])
        # Handle response structure safely
        tasks = data.get("tasks", [])
        if not tasks or not tasks[0].get("result"):
            print(f"[ai_mentions] No results in response for {domain}")
            return []
        
        items = tasks[0]["result"][0].get("items", [])
        results = []
        for item in items:
            results.append({
                "source": item.get("source", ""),
                "query": item.get("query", ""),
                "mention_type": item.get("mention_type", ""),
                "cited_url": item.get("cited_url", ""),
                "cited_title": item.get("cited_title", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("date", ""),
            })
        return results
    return _run(_inner())


def ai_mentions_keywords(
    keywords: list[str],
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 100,
) -> list[dict]:
    """AI-engine answers that mention the given KEYWORDS (ChatGPT + Google AI).

    One call covers up to 10 head terms. Each returned item is one
    question an AI engine answered, with its answer, cited sources and
    AI search volume — the raw material for the AI-citability stage.
    """
    clean = [k.strip() for k in (keywords or []) if isinstance(k, str) and k.strip()][:10]
    if not clean:
        return []

    async def _inner():
        data = await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [
            {
                "target": [
                    {
                        "keyword": kw,
                        "search_filter": "include",
                        "search_scope": ["any"],
                        "match_type": "word_match",
                    }
                    for kw in clean
                ],
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ])
        tasks = data.get("tasks", [])
        if not tasks or not tasks[0].get("result"):
            return []
        items = tasks[0]["result"][0].get("items", [])
        results = []
        for item in items:
            sources = []
            for s in (item.get("sources") or [])[:5]:
                sources.append({
                    "domain": s.get("domain", ""),
                    "url": s.get("url", ""),
                    "title": s.get("title", ""),
                })
            results.append({
                "platform": item.get("platform", ""),
                "model_name": item.get("model_name", ""),
                "question": item.get("question", ""),
                "answer_snippet": (item.get("answer") or "")[:300],
                "has_answer": bool((item.get("answer") or "").strip()),
                "sources": sources,
                "ai_search_volume": item.get("ai_search_volume") or 0,
            })
        return results
    return _run(_inner())


def serp_paa(keyword: str, location_code: int = 2840, language_code: str = "en") -> list[dict]:
    """People-also-ask questions for a keyword, from SERP advanced (free add-on to the SERP call)."""
    async def _inner():
        data = await _post("/v3/serp/google/organic/live/advanced", [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "depth": 20,
            }
        ])
        items = _task_items(data)
        questions = []
        for item in items:
            if item.get("type") != "people_also_ask":
                continue
            for sub in item.get("items", []) or []:
                title = sub.get("title") or ""
                if title:
                    questions.append({
                        "question": title,
                        "domain": sub.get("domain", ""),
                        "url": sub.get("url", ""),
                    })
            # some payloads carry the question at top level
            if not item.get("items") and item.get("title"):
                questions.append({"question": item.get("title", ""), "domain": item.get("domain", ""), "url": item.get("url", "")})
        return questions[:12]
    return _run(_inner())


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
