"""Explicit market (country + language) confirmation.

The single biggest correctness failure we shipped was inferring the market
from a domain: a .bg site was assumed to be a Bulgarian-language business, the
seeds came out transliterated, and the thin-market competitor ladder then
pulled in whatever ranked in BG — theatre listings for a poetry site. The
fallback ladder was working exactly as designed; it was fed a guessed market.

So the market is never inferred. It is confirmed by the user, validated
against DataForSEO's own locations_and_languages, and pinned to the run.
`run_keyword_strategy` refuses to start without one.
"""
from __future__ import annotations

import threading

# Markets we offer by name. location_code is DataForSEO's Google location.
# `languages` lists the plausible search languages for that market, most
# common first — the actual set is validated against DFS before we accept it.
MARKETS: dict[str, dict] = {
    "US": {"code": 2840, "country": "United States", "languages": ["en", "es"]},
    "UK": {"code": 2826, "country": "United Kingdom", "languages": ["en"]},
    "IE": {"code": 2724, "country": "Ireland", "languages": ["en"]},
    "CA": {"code": 2124, "country": "Canada", "languages": ["en", "fr"]},
    "AU": {"code": 2036, "country": "Australia", "languages": ["en"]},
    "DE": {"code": 2276, "country": "Germany", "languages": ["de", "en"]},
    "FR": {"code": 2250, "country": "France", "languages": ["fr", "en"]},
    "ES": {"code": 2704, "country": "Spain", "languages": ["es", "en"]},
    "IT": {"code": 2380, "country": "Italy", "languages": ["it", "en"]},
    "NL": {"code": 2528, "country": "Netherlands", "languages": ["nl", "en"]},
    "BE": {"code": 2056, "country": "Belgium", "languages": ["nl", "fr", "en"]},
    "PL": {"code": 2616, "country": "Poland", "languages": ["pl", "en"]},
    "RO": {"code": 2642, "country": "Romania", "languages": ["ro", "en"]},
    "GR": {"code": 2300, "country": "Greece", "languages": ["el", "en"]},
    "BG": {"code": 2100, "country": "Bulgaria", "languages": ["bg", "en"]},
}

_BY_CODE = {m["code"]: (key, m) for key, m in MARKETS.items()}

# Confirmed markets, keyed by run id. Set only via confirm_market().
_confirmed: dict[str, dict] = {}
_lock = threading.Lock()


class MarketNotConfirmed(Exception):
    """Raised when strategy work starts without a user-confirmed market."""


def catalog() -> list[dict]:
    """The offerable markets, for a picker in chat / the UI / WebMCP."""
    return [
        {"market": key, "country": m["country"], "location_code": m["code"],
         "languages": m["languages"]}
        for key, m in MARKETS.items()
    ]


def _lookup(country: str) -> tuple[str, dict] | None:
    """Resolve a country by ISO code, name, or DFS location code."""
    raw = str(country or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return _BY_CODE.get(int(raw))
    key = raw.upper()
    if key in MARKETS:
        return key, MARKETS[key]
    lowered = raw.lower()
    for k, m in MARKETS.items():
        if m["country"].lower() == lowered:
            return k, m
    return None


def _supported_languages(location_code: int) -> list[str]:
    """Languages DataForSEO actually serves for this location ([] if unknown)."""
    try:
        from .tools.dataforseo import _location_languages, _run

        return list(_run(_location_languages()).get(location_code) or [])
    except Exception:
        # Never let a DFS outage block market confirmation — fall back to the
        # curated list and let the existing 40501 retry path handle a miss.
        return []


def resolve(country: str, language: str) -> dict:
    """Validate a country + language pair without pinning it to a run.

    Returns {ok, location_code, language_code, market, country, ...} or
    {ok: False, error, ...} with the choices that would have been valid.
    """
    found = _lookup(country)
    if not found:
        return {
            "ok": False,
            "error": f"Unknown country {country!r}.",
            "available_markets": catalog(),
        }
    key, market = found
    code = market["code"]

    lang = str(language or "").strip().lower()
    if not lang:
        return {
            "ok": False,
            "error": f"Language is required for {market['country']} — ask the user, "
                     f"do not infer it from the domain or the site's content.",
            "market": key,
            "location_code": code,
            "suggested_languages": market["languages"],
        }

    supported = _supported_languages(code)
    if supported and lang not in supported:
        return {
            "ok": False,
            "error": f"DataForSEO does not serve '{lang}' keyword data for "
                     f"{market['country']}.",
            "market": key,
            "location_code": code,
            "supported_languages": supported[:10],
        }

    return {
        "ok": True,
        "market": key,
        "country": market["country"],
        "location_code": code,
        "language_code": lang,
        "label": f"{key}-{lang.upper()}",
    }


def confirm_market(country: str, language: str, run_id: str | None = None) -> dict:
    """Pin a user-confirmed country + language to the active run.

    Call this ONLY after the user has stated both explicitly. Never infer them
    from a domain, a TLD, or the language the user happens to be typing in.
    """
    from . import pipeline_recorder as rec

    resolved = resolve(country, language)
    if not resolved.get("ok"):
        return resolved

    rid = run_id or rec.active_run_id()
    if rid:
        with _lock:
            _confirmed[rid] = resolved
        rec.record_tool(
            "confirm_market",
            {"location_code": resolved["location_code"],
             "language_code": resolved["language_code"]},
            resolved, True,
        )
        rec.log_activity("step", detail=f"market confirmed: {resolved['label']}")

    return resolved


def confirmed_market(run_id: str | None = None) -> dict | None:
    """The market pinned to this run, or None if the user never confirmed one."""
    from . import pipeline_recorder as rec

    rid = run_id or rec.active_run_id()
    if not rid:
        return None
    with _lock:
        return _confirmed.get(rid)


def require_market(
    location_code: int | None = None,
    language_code: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Resolve the market strategy work must run in, or raise.

    A confirmed market always wins. Explicit arguments are accepted only when
    they match it — an LLM passing a different location_code cannot silently
    override what the user chose.
    """
    pinned = confirmed_market(run_id)
    if pinned:
        if location_code and location_code != pinned["location_code"]:
            raise MarketNotConfirmed(
                f"This run is pinned to {pinned['label']} "
                f"(location {pinned['location_code']}), but location_code "
                f"{location_code} was passed. Ask the user before changing market."
            )
        return pinned

    raise MarketNotConfirmed(
        "No market confirmed for this run. Ask the user which COUNTRY and which "
        "LANGUAGE to target — never infer them from the domain, the TLD, or the "
        "language of the conversation — then call confirm_market(country, "
        "language) before any keyword research. "
        f"Offerable markets: {', '.join(sorted(MARKETS))}."
    )


def reset(run_id: str) -> None:
    """Drop a run's pinned market (tests, and re-targeting a finished run)."""
    with _lock:
        _confirmed.pop(run_id, None)
