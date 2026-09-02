"""Competitor URLs are used on every run, not only when the market is thin.

Before: a run with 44 keywords never touched the competitor URLs the user
typed in — the only thing it got from them was what the model guessed from
the domain names. Now every run pulls what the competition ranks for, tags
each keyword with its owners, and computes the consensus set (ranked by two
or more competitors), which is the real gap for a site that ranks for nothing.
"""
import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.tools import pull_universe as pu  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAILED: {label}"
    PASS += 1


calls = []


def fake_keywords_for_site(domain, limit=100):
    calls.append(("ranked", domain, limit))
    data = {
        "productpirates.club": [],  # the new site ranks for nothing
        "lennysnewsletter.com": [{"keyword": "product manager", "volume": 5000},
                                 {"keyword": "ai product manager", "volume": 900},
                                 {"keyword": "product strategy", "volume": 1200}],
        "productschool.com": [{"keyword": "ai product manager", "volume": 900},
                              {"keyword": "product manager certification", "volume": 2000},
                              {"keyword": "product strategy", "volume": 1200}],
        "mindtheproduct.com": [{"keyword": "product strategy", "volume": 1200},
                               {"keyword": "product discovery", "volume": 700}],
        "auto1.com": [{"keyword": "auto only", "volume": 10}],
        "auto2.com": [{"keyword": "auto two", "volume": 20}],
    }
    return [dict(r) for r in data.get(domain, [])]


def fake_competitors_domain(domain, limit=10):
    calls.append(("discover", domain, limit))
    return ["auto1.com", "www.auto2.com", "lennysnewsletter.com", "auto3.com"]


def fake_intersection(a, b, limit=50):
    calls.append(("intersect", a, b))
    return [{"keyword": "product strategy", "volume": 1200}]


def fake_budget():
    return 99


ctx = lambda: (  # noqa: E731
    patch.object(pu.dfs, "keywords_for_site", fake_keywords_for_site),
    patch.object(pu.dfs, "competitors_domain", fake_competitors_domain),
    patch.object(pu.dfs, "domain_intersection", fake_intersection),
    patch.object(pu.dfs, "budget_remaining", fake_budget),
)


def run(**kw):
    calls.clear()
    ps = ctx()
    for p in ps:
        p.start()
    try:
        return pu._competitor_universe(
            kw.get("urls", []), kw.get("site", ""), 2840, "en")
    finally:
        for p in ps:
            p.stop()


print("1. user-supplied competitors are queried, user first")
m = run(urls=["https://www.lennysnewsletter.com/", "productschool.com", "https://mindtheproduct.com/blog"],
        site="https://productpirates.club/")
ok(m["user"] == ["lennysnewsletter.com", "productschool.com", "mindtheproduct.com"], "URLs normalised to domains")
ok(m["queried"][:3] == m["user"], "user-supplied domains come first")
ok(len(m["queried"]) == 5, f"filled to 5 with discovery, got {m['queried']}")
ok(m["discovered"] == ["auto1.com", "auto2.com"], f"discovery added the two that were new and not already supplied, got {m['discovered']}")
ok(("discover", "productpirates.club", 10) in calls, "discovery ran against the site")
ok(m["site_has_rankings"] is False, "the site was checked and ranks for nothing")
ok(not any(c[0] == "intersect" for c in calls), "no intersection calls for a site with no rankings")
ranked = [c for c in calls if c[0] == "ranked" and c[1] != "productpirates.club"]
ok(len(ranked) == 5 and all(c[2] == 100 for c in ranked), "one ranked_keywords call per queried domain")

print("2. rows are tagged and consensus is computed")
rows = {r["keyword"]: r for r in m["_rows"]}
ok(rows["product strategy"]["owned_by"] == ["lennysnewsletter.com", "productschool.com", "mindtheproduct.com"],
   "a keyword three competitors rank for lists all three owners")
ok(rows["product strategy"]["consensus"] == 3, "consensus count is the number of owners")
ok(rows["product discovery"].get("consensus") is None and rows["product discovery"]["owned_by"] == ["mindtheproduct.com"],
   "a single-owner keyword is not consensus")
ok(all(r["source"] == "competitor" for r in m["_rows"]), "every row says where it came from")
ok(m["consensus"][0]["keyword"] == "product strategy" and m["consensus"][0]["owned_by"] == sorted(rows["product strategy"]["owned_by"]),
   "consensus list leads with the most-shared keyword")
ok([c["keyword"] for c in m["consensus"]][:2] == ["product strategy", "ai product manager"],
   "then by owners, then by volume")
ok(m["keywords_contributed"] == len(m["_rows"]) == 7, f"seven unique keywords contributed, got {m['keywords_contributed']}")
ok(m["per_domain"]["lennysnewsletter.com"]["keywords"] == 3, "per-domain counts recorded")

print("3. intersection runs only when the site has rankings")
with patch.object(pu.dfs, "keywords_for_site",
                  lambda d, limit=100: [{"keyword": "x", "volume": 1}] if d == "productpirates.club" else fake_keywords_for_site(d, limit)):
    ps = ctx()[1:]
    for p in ps: p.start()
    try:
        calls.clear()
        m2 = pu._competitor_universe(["lennysnewsletter.com"], "productpirates.club", 2840, "en")
    finally:
        for p in ps: p.stop()
ok(m2["site_has_rankings"] is True, "site with rankings detected")
ok(("intersect", "productpirates.club", "lennysnewsletter.com") in calls, "intersection ran for a ranking site")
ok(m2["per_domain"]["lennysnewsletter.com"]["shared_with_site"] == 1, "shared count recorded")
ok(next(r for r in m2["_rows"] if r["keyword"] == "product strategy").get("site_ranks_too") is True,
   "shared keyword is flagged on the row")

print("4. caps and edges")
m3 = run(urls=[f"https://c{i}.com" for i in range(12)], site="")
ok(len(m3["user"]) == 12 or len(m3["user"]) <= pu.MAX_COMPETITOR_URLS, "pull_universe caps at 10 before this point")
ok(len(m3["queried"]) == 5, "at most 5 queried")
ok(not any(c[0] == "discover" for c in calls), "no discovery without a site")
m4 = run(urls=[], site="")
ok(m4["queried"] == [] and m4["_rows"] == [], "nothing to do with no competitors and no site")
m5 = run(urls=["https://productpirates.club/about"], site="productpirates.club")
ok("productpirates.club" not in m5["queried"], "the site itself is never treated as a competitor")

print("5. through pull_universe: always-on, thin fallback suppressed, map returned")
with patch.object(pu, "_expand_seed", lambda *a, **k: [{"keyword": f"seed kw {i}", "volume": 30} for i in range(20)]), \
     patch.object(pu, "_competitor_keywords", lambda *a, **k: (_ for _ in ()).throw(AssertionError("thin fallback must not run"))):
    ps = ctx()
    for p in ps: p.start()
    try:
        calls.clear()
        out = pu.pull_universe({"business_seeds": ["a"]}, 2840, "en",
                               competitor_urls=["lennysnewsletter.com"], site_url="productpirates.club")
    finally:
        for p in ps: p.stop()
ok(any(c[0] == "ranked" and c[1] == "lennysnewsletter.com" for c in calls), "competitors queried even with 20 seed keywords (not thin)")
ok(out["competitors"]["queried"], "the map is returned on the universe")
ok("_rows" not in out["competitors"], "the raw rows are not duplicated into the map")
kws = {k["keyword"] for k in out["keywords"]}
ok("product strategy" in kws and "seed kw 0" in kws, "competitor keywords merged with seed expansion")
ok(len(pu.MAX_COMPETITOR_URLS.__class__.__name__) and pu.MAX_COMPETITOR_URLS == 10, "the accepted cap is 10")

print("6. a competitor's own brand terms are not topics")
ok(pu._is_brand_term("lenny podcast", "lennysnewsletter.com"), "short stem matches: lenny -> lennysnewsletter")
ok(pu._is_brand_term("lennys newsletter pricing", "www.lennysnewsletter.com"), "full label matches")
ok(pu._is_brand_term("maven", "maven.com"), "the bare brand")
ok(pu._is_brand_term("aiproducts", "aiproduct.com"), "label inside a compact keyword")
ok(not pu._is_brand_term("ai product management", "aiproduct.com"), "a topical phrase with a space is not the brand")
ok(not pu._is_brand_term("product strategy", "lennysnewsletter.com"), "an ordinary topic passes")
ok(not pu._is_brand_term("mind the product", "mtp.com"), "a stem under five letters is never used")

with patch.object(pu.dfs, "keywords_for_site", lambda d, limit=100: [
        {"keyword": "lenny podcast", "volume": 4400}, {"keyword": "product strategy", "volume": 1200},
        {"keyword": "lennys newsletter", "volume": 9000}] if d == "lennysnewsletter.com" else []),      patch.object(pu.dfs, "competitors_domain", lambda d, limit=10: []),      patch.object(pu.dfs, "domain_intersection", lambda a, b, limit=50: []),      patch.object(pu.dfs, "budget_remaining", lambda: 9):
    m6 = pu._competitor_universe(["lennysnewsletter.com"], "", 2840, "en")
ok([r["keyword"] for r in m6["_rows"]] == ["product strategy"], "brand rows never enter the universe")
ok(m6["per_domain"]["lennysnewsletter.com"]["brand_terms_skipped"] == 2, "and the map counts what was skipped")
ok(m6["per_domain"]["lennysnewsletter.com"]["keywords"] == 1, "the keyword count is the topical count")
ok([r["keyword"] for r in m6["per_domain"]["lennysnewsletter.com"]["rows"]] == ["product strategy"], "the stored list is topical too")

print("7. the relevance gate")
rows7 = [{"keyword": "ai product management", "volume": 480}, {"keyword": "lenny job board", "volume": 4400},
         {"keyword": "product strategy", "volume": 1200}, {"keyword": "cybersecurity product", "volume": 1000}]
with patch.object(pu.llm, "chat", lambda *a, **k: "ignored"), \
     patch.object(pu.llm, "parse_json_response", lambda r: {"keep": [1, 3], "dropped_because": "job board and cybersecurity are not this business"}):
    kept, gate = pu._relevance_gate(rows7, "An AI community of practice for product managers")
ok([r["keyword"] for r in kept] == ["ai product management", "product strategy"], "keeps what the model keeps, by number")
ok(gate["ran"] and gate["kept"] == 2 and gate["dropped"] == 2, "the map records the counts")
ok(gate["dropped_examples"][0] == "lenny job board", "dropped examples lead with the biggest")
ok("job board" in gate["dropped_because"], "and the model's one-line reason")

with patch.object(pu.llm, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout"))):
    kept, gate = pu._relevance_gate(rows7, "a business")
ok(len(kept) == 4 and gate["ran"] is False and "timeout" in gate["error"], "fails open, and says so")

with patch.object(pu.llm, "chat", lambda *a, **k: "x"), patch.object(pu.llm, "parse_json_response", lambda r: {"keep": []}):
    kept, gate = pu._relevance_gate(rows7, "a business")
ok(len(kept) == 4 and "cannot be right" in gate["note"], "a model that keeps nothing does not empty the universe")

kept, gate = pu._relevance_gate(rows7, "")
ok(len(kept) == 4 and gate["ran"] is False, "no business description: nothing to judge against, all kept")

print(f"competitors: {PASS} assertions passed")
