"""Full allowed-values message, and what a DOMAIN target with scope=sources does."""
import sys, json
from collections import Counter
sys.path.insert(0, '.')
from src.tools.dataforseo import _post, _run

async def probe(target, scope):
    return await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [{
        "target": [dict(target, search_filter="include", search_scope=scope,
                        match_type="word_match")],
        "location_code": 2840, "language_code": "en", "limit": 20,
    }])

print("1. full allowed-values message for a KEYWORD target")
try:
    d = _run(probe({"keyword": "llm evaluation"}, ["sources"]))
    t = (d.get("tasks") or [{}])[0]
    print("   ", str(t.get("status_message"))[:400])
except Exception as e:
    print("   ERR", e)

print("\n2. DOMAIN target with scope=sources — 'where is this domain cited?'")
for dom in ("www.evidentlyai.com", "stripe.com"):
    for scope in (["sources"], ["answer"]):
        try:
            d = _run(probe({"domain": dom}, scope))
            t = (d.get("tasks") or [{}])[0]
            if t.get("status_code") != 20000:
                print(f"   {dom:<22} {str(scope):<12} error {t.get('status_code')}: "
                      f"{str(t.get('status_message'))[:90]}")
                continue
            res = (t.get("result") or [{}])[0]
            items = res.get("items") or []
            qs = [(i.get("question") or "")[:40] for i in items[:3]]
            print(f"   {dom:<22} {str(scope):<12} total={res.get('total_count')} items={len(items)}")
            for q in qs:
                print(f"        cited for: {q!r}")
        except Exception as e:
            print(f"   {dom:<22} {str(scope):<12} ERR {str(e)[:70]}")
