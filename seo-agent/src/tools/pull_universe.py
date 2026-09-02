from __future__ import annotations

from urllib.parse import urlparse

from . import dataforseo as dfs
from .. import llm
from ..config import settings
from .cache import get_cached, set_cached

# Below this many deduped keywords the market is "thin" and we escalate to
# competitor discovery so the strategy graph still has material to work with.
THIN_THRESHOLD = 15

# Competitor handling. Up to MAX_COMPETITOR_URLS supplied URLs are accepted;
# the first MAX_COMPETITORS_QUERIED are queried (user-supplied first), and
# when a site is given, DataForSEO's own competitor discovery fills any
# remaining slots. Each queried domain costs one ranked_keywords call, plus
# one domain_intersection call IF the site itself has rankings to intersect.
MAX_COMPETITOR_URLS = 10
MAX_COMPETITORS_QUERIED = 5
COMPETITOR_KEYWORDS_PER_DOMAIN = 100
# Cap direct seed expansion to keep the DataForSEO budget sane on wide briefs.
MAX_EXPAND_SEEDS = 5


def pull_universe(
    seeds: dict,
    location_code: int = 2840,
    language_code: str = "en",
    competitor_urls: list[str] = None,
    site_url: str = "",
    business_description: str = "",
) -> dict:
    """Expand keyword seeds into a full keyword universe using DataForSEO.

    Thin-market resilience: some languages/niches have few or no related
    keywords (e.g. "изречена поезия" in Bulgarian). When direct expansion
    comes back thin we fall back to what competitors rank for, and we always
    keep the seeds themselves in the universe so the strategy graph never
    runs dry.
    """
    competitor_urls = (competitor_urls or [])[:MAX_COMPETITOR_URLS]
    all_keywords: list[dict] = []

    # ---- Ladder 1: direct seed expansion (related + suggestions) ----
    expand_seeds = _collect_seeds(seeds)[:MAX_EXPAND_SEEDS]
    for seed in expand_seeds:
        all_keywords.extend(_expand_seed(seed, location_code, language_code))

    # ---- Ladder 2: trending keywords ----
    # Disabled: the DFS trending_keywords endpoint 404s (does not exist), so the
    # call only ever burned budget. Re-enable once a working endpoint is wired.
    # all_keywords.extend(_trending(location_code, language_code))

    # ---- Ladder 2: what competitors rank for — always, not only when thin ----
    # This used to be an emergency fallback that fired only under 15 keywords,
    # so a normal run never touched the competitor URLs the user typed in; all
    # it got from them was whatever the model guessed from the domain names.
    # What the competition actually ranks for is the strongest signal in the
    # whole universe, and it belongs in every run.
    competitor_map = _competitor_universe(competitor_urls, site_url, location_code, language_code)
    comp_rows = competitor_map.pop("_rows", [])
    # Semantic gate. Consensus and volume say what the competition wins; they
    # say nothing about whether it is YOUR topic. "lenny job board" has
    # volume and a competitor ranks for it, and it has no business in a
    # universe that feeds this business's pillars.
    comp_rows, gate = _relevance_gate(comp_rows, business_description)
    if isinstance(competitor_map, dict):
        competitor_map["relevance"] = gate
    all_keywords.extend(comp_rows)

    # Always keep the seeds themselves as a floor. In thin markets these are
    # often the only usable terms — the discovery-input keyword survives even
    # when the APIs return nothing for it.
    all_keywords.extend(_seeds_as_keywords(seeds))

    unique = _dedupe(all_keywords)

    # ---- Ladder 3: thin market -> competitor discovery ----
    if len(unique) < THIN_THRESHOLD and dfs.budget_remaining() > 0 and not competitor_map.get("queried"):
        print(f"  [pull_universe] thin market ({len(unique)} keywords) -> competitor discovery")
        comp_keywords = _competitor_keywords(
            expand_seeds, competitor_urls, location_code, language_code
        )
        all_keywords.extend(comp_keywords)
        unique = _dedupe(all_keywords)

    # Sort by volume (handle None values); seeds/competitor rows with no
    # volume sink to the bottom in rich markets but carry thin ones.
    unique.sort(key=lambda x: x.get("volume") or 0, reverse=True)

    # Balance. Three competitors at 100 keywords each out-number the seed
    # expansion several times over, and a plain top-200-by-volume cut then
    # keeps mostly theirs — the strategy stops being about the business the
    # user described. Seed-derived keywords lead; competitor keywords fill up
    # to the same number, consensus (shared by 2+ competitors) first, then by
    # volume. The map records what was kept so the report can say so.
    seed_rows = [k for k in unique if k.get("source") != "competitor"]
    comp_rows = [k for k in unique if k.get("source") == "competitor"]
    comp_rows.sort(key=lambda k: (-(k.get("consensus") or 0), -(k.get("volume") or 0)))
    seed_keep = seed_rows[:200]
    comp_keep = comp_rows[:max(0, min(len(seed_keep), 200 - len(seed_keep)))]
    _backfill_difficulty(comp_keep, location_code, language_code)
    kept = sorted(seed_keep + comp_keep, key=lambda k: -(k.get("volume") or 0))
    if isinstance(competitor_map, dict):
        competitor_map["kept_in_universe"] = len(comp_keep)
        competitor_map["seed_derived_in_universe"] = len(seed_keep)
    return {
        "keywords": kept,
        "total_count": len(unique),
        "competitors": competitor_map,
    }


def _backfill_difficulty(rows: list[dict], location_code: int, language_code: str) -> None:
    """The ranked-keywords endpoint does not always carry difficulty. One bulk
    call fills it for the rows that survived the cut, so a competitor keyword
    shows KD like every other row. One call, not one per keyword."""
    missing = [r for r in rows if r.get("difficulty") in (None, 0) and r.get("keyword")]
    if not missing or dfs.budget_remaining() <= 0:
        return
    try:
        kd = dfs.bulk_keyword_difficulty([r["keyword"] for r in missing],
                                         location_code=location_code, language_code=language_code)
    except Exception as e:
        print(f"  [WARN] bulk difficulty backfill failed: {e}")
        return
    for r in missing:
        v = kd.get(r["keyword"].lower())
        if v is not None:
            r["difficulty"] = v


def _collect_seeds(seeds: dict) -> list[str]:
    """Interleave seed categories so a budget cut spans all three.

    Flattening business -> site -> competitor and then taking the first
    MAX_EXPAND_SEEDS meant the budget was spent almost entirely on business
    seeds. Observed 2026-09-01 on productpirates.club: four generic
    "AI product manager" seeds were expanded and the distinctive site seeds
    ("agentic commerce building blocks", "open source LLM evaluation",
    "remote home computer access") were never expanded at all. The universe
    came back as an AI-PM job board and the strategy followed it there.

    Round-robin instead: every category contributes before any repeats.
    """
    buckets = [
        [str(x).strip() for x in (seeds.get("business_seeds") or []) if str(x).strip()],
        [str(x).strip() for x in (seeds.get("site_seeds") or []) if str(x).strip()],
        [str(x).strip() for x in (seeds.get("competitor_seeds") or []) if str(x).strip()],
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for i in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if i >= len(bucket):
                continue
            seed = bucket[i]
            key = seed.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(seed)
    return ordered


def _expand_seed(seed: str, location_code: int, language_code: str) -> list[dict]:
    """Related keywords + suggestions for one seed, cache-backed.

    Each keyword is tagged with the seed that produced it so later stages can
    keep coverage across seeds instead of letting one high-volume seed's
    expansion crowd everything else out.
    """
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

    for kw in results:
        if isinstance(kw, dict):
            kw.setdefault("source_seed", seed)

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


def _competitor_universe(
    competitor_urls: list[str],
    site_url: str,
    location_code: int,
    language_code: str,
) -> dict:
    """What the competition ranks for, with every keyword tagged by owner.

    Returns a map for the report plus the keyword rows under "_rows":
      user        — domains the user supplied (up to MAX_COMPETITOR_URLS)
      discovered  — domains DataForSEO found competing with the site
      queried     — the domains actually looked up, user-supplied first
      per_domain  — keywords contributed by each, and how many the site shares
      consensus   — keywords ranked by TWO OR MORE competitors: where the
                    space competes, which is the gap for a site that ranks for
                    nothing yet
      site_has_rankings — whether domain_intersection was worth calling

    domain_intersection(site, competitor) returns keywords BOTH rank for. A
    new site ranks for nothing, so that call is an empty result at full price;
    it runs only after one cheap check shows the site has rankings at all.
    """
    empty = {"user": [], "discovered": [], "queried": [], "per_domain": {},
             "consensus": [], "site_has_rankings": None, "_rows": []}
    domains: list[str] = []
    seen = set()

    def _add(domain: str) -> None:
        d = (domain or "").lower().strip().removeprefix("www.")
        if d and d not in seen and d != site_domain:
            seen.add(d)
            domains.append(d)

    site_domain = _domain_of(site_url).lower().removeprefix("www.") if site_url else ""
    user = []
    for url in competitor_urls:
        d = _domain_of(url).lower().removeprefix("www.")
        if d:
            user.append(d)
            _add(d)
    result = dict(empty, user=user)
    if not domains and not site_domain:
        return result

    # Fill remaining slots from DataForSEO's own competitor discovery.
    if site_domain and len(domains) < MAX_COMPETITORS_QUERIED and dfs.budget_remaining() > 0:
        try:
            found = dfs.competitors_domain(site_domain, limit=MAX_COMPETITORS_QUERIED * 2)
        except Exception as e:
            print(f"  [WARN] competitors_domain failed for '{site_domain}': {e}")
            found = []
        for d in found:
            if len(domains) >= MAX_COMPETITORS_QUERIED:
                break
            before = len(domains)
            _add(d)
            if len(domains) > before:
                result["discovered"].append(domains[-1])

    queried = domains[:MAX_COMPETITORS_QUERIED]
    result["queried"] = queried
    if not queried:
        return result

    # One cheap check decides whether intersection is worth paying for.
    site_has_rankings = None
    if site_domain and dfs.budget_remaining() > 0:
        try:
            site_has_rankings = bool(dfs.keywords_for_site(site_domain, limit=1))
        except Exception as e:
            print(f"  [WARN] keywords_for_site failed for site '{site_domain}': {e}")
    result["site_has_rankings"] = site_has_rankings

    owners: dict[str, set] = {}
    rows_by_kw: dict[str, dict] = {}
    for domain in queried:
        if dfs.budget_remaining() <= 0:
            print("  [pull_universe] DFS budget exhausted before competitor lookups finished")
            break
        try:
            kws = dfs.keywords_for_site(domain, limit=COMPETITOR_KEYWORDS_PER_DOMAIN)
        except Exception as e:
            print(f"  [WARN] keywords_for_site failed for '{domain}': {e}")
            kws = []
        shared = []
        if kws and site_has_rankings and dfs.budget_remaining() > 0:
            try:
                shared = dfs.domain_intersection(site_domain, domain, limit=50)
            except Exception as e:
                print(f"  [WARN] domain_intersection failed for '{domain}': {e}")
        shared_set = {(r.get("keyword") or "").lower() for r in shared}
        # A competitor's own brand terms ("lenny podcast", "maven") are
        # navigational for THEM; nobody else can win them and they only crowd
        # out the topical keywords. Dropped, and counted, so the map says so.
        brand_hits = 0
        for kw in kws:
            key = (kw.get("keyword") or "").strip().lower()
            if not key:
                continue
            if _is_brand_term(key, domain):
                brand_hits += 1
                continue
            owners.setdefault(key, set()).add(domain)
            row = rows_by_kw.get(key)
            if row is None:
                row = dict(kw)
                row["source"] = "competitor"
                row["owned_by"] = []
                rows_by_kw[key] = row
            row["owned_by"].append(domain)
            if key in shared_set:
                row["site_ranks_too"] = True
        result["per_domain"][domain] = {
            "keywords": len(kws) - brand_hits,
            "brand_terms_skipped": brand_hits,
            "shared_with_site": len(shared_set),
            "top": [k.get("keyword") for k in kws[:5]],
            # The whole list, so the report can show what each one ranks for
            # and draw the overlap between them. ~100 small rows per domain.
            "rows": [
                {"keyword": k.get("keyword"), "volume": k.get("volume"),
                 "difficulty": k.get("difficulty"), "cpc": k.get("cpc"),
                 "intent": k.get("intent"), "rank": k.get("rank")}
                for k in kws
                if not _is_brand_term((k.get("keyword") or "").lower(), domain)
            ],
        }
        print(f"  [pull_universe] competitor '{domain}' contributed {len(kws)} keywords"
              + (f", {len(shared_set)} shared with the site" if shared_set else ""))

    consensus = sorted(
        (k for k, o in owners.items() if len(o) >= 2),
        key=lambda k: (-len(owners[k]), -(rows_by_kw[k].get("volume") or 0)),
    )
    result["consensus"] = [
        {"keyword": rows_by_kw[k].get("keyword"), "volume": rows_by_kw[k].get("volume"),
         "owned_by": sorted(owners[k])}
        for k in consensus[:40]
    ]
    for k in consensus:
        rows_by_kw[k]["consensus"] = len(owners[k])
    result["_rows"] = list(rows_by_kw.values())
    result["keywords_contributed"] = len(rows_by_kw)
    return result


_GENERIC = {
    "product", "products", "ai", "the", "school", "news", "newsletter", "blog", "app",
    "apps", "hq", "web", "dev", "tech", "data", "cloud", "lab", "labs", "media", "digital",
    "online", "official", "podcast", "mind", "guide", "guides", "tools", "tool", "hub",
}
_SUFFIXES = ("newsletter", "school", "blog", "labs", "media", "digital", "online", "official",
             "podcast", "hq", "app", "ai", "io")


RELEVANCE_SYSTEM = """You are an SEO strategist. You are given a business and a numbered list of
keywords that its COMPETITORS rank for. Keep only the keywords a reader of this
business would plausibly be searching for — topics this business could
legitimately write about. Drop keywords about the competitor itself (its name,
products, people, jobs, pricing), unrelated industries, and generic phrases
with no connection to the business.

Answer with JSON only:
{"keep": [numbers], "dropped_because": "one short sentence on what you removed"}"""


def _relevance_gate(rows: list[dict], business_description: str) -> tuple[list[dict], dict]:
    """Keep the competitor keywords that are about this business's topics.

    One call on the fast model, index-encoded so the answer is a list of
    numbers rather than the keywords repeated back. Fails OPEN: if the model
    call breaks, every row is kept and the map says the gate did not run —
    a silent drop would be worse than a noisy universe.
    """
    if not rows or not (business_description or "").strip():
        return rows, {"ran": False, "kept": len(rows), "dropped": 0}

    listing = "\n".join(f"{i + 1}. {r.get('keyword', '')}" for i, r in enumerate(rows[:300]))
    user_msg = f"The business:\n{business_description.strip()[:1500]}\n\nCompetitor keywords:\n{listing}"
    try:
        resp = llm.chat(user_msg, system=RELEVANCE_SYSTEM, model=settings.qwen_model_fast,
                        temperature=0, max_tokens=1200)
        data = llm.parse_json_response(resp)
        keep = data.get("keep") if isinstance(data, dict) else None
        if not isinstance(keep, list):
            raise ValueError("no keep list")
        keep_idx = {int(i) - 1 for i in keep if str(i).lstrip("-").isdigit()}
    except Exception as e:
        print(f"  [pull_universe] relevance gate did not run: {e}")
        return rows, {"ran": False, "kept": len(rows), "dropped": 0, "error": str(e)[:120]}

    kept = [r for i, r in enumerate(rows) if i in keep_idx or i >= 300]
    dropped = [r for i, r in enumerate(rows) if i not in keep_idx and i < 300]
    # A model that keeps nothing has misread the task; do not empty the universe on it.
    if not kept and rows:
        return rows, {"ran": True, "kept": len(rows), "dropped": 0,
                      "note": "the model kept nothing, which cannot be right — all rows retained"}
    gate = {
        "ran": True,
        "kept": len(kept),
        "dropped": len(dropped),
        "dropped_because": str((data.get("dropped_because") if isinstance(data, dict) else "") or "")[:200],
        "dropped_examples": [r.get("keyword") for r in
                             sorted(dropped, key=lambda r: -(r.get("volume") or 0))[:8]],
    }
    print(f"  [pull_universe] relevance gate kept {len(kept)}/{len(rows)} competitor keywords")
    return kept, gate


def _brand_tokens(domain: str) -> set[str]:
    """Words that mean the competitor itself. From lennysnewsletter.com:
    lennysnewsletter, lennys, lenny. From productschool.com: only
    productschool — "product" is a topic word, not a brand."""
    label = (domain or "").lower().removeprefix("www.").split(".")[0]
    if not label:
        return set()
    cands = {label, label + "s"}
    if label.endswith("s"):
        cands.add(label[:-1])
    for suf in _SUFFIXES:
        if label.endswith(suf) and len(label) > len(suf) + 3:
            prefix = label[: -len(suf)]
            cands.add(prefix)
            if prefix.endswith("s"):
                cands.add(prefix[:-1])
    return {t for t in cands if len(t) >= 4 and t not in _GENERIC}


def _is_brand_term(keyword: str, domain: str) -> bool:
    """True when a keyword is about the competitor itself rather than a topic:
    a whole word equals a brand token, or the keyword collapsed to one word
    IS the brand ("lennys newsletter", "aiproducts")."""
    tokens = _brand_tokens(domain)
    if not tokens:
        return False
    kw = keyword.lower().replace("'", "").replace("-", " ")
    words = kw.split()
    compact = "".join(words)
    return any(w in tokens for w in words) or compact in tokens


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
