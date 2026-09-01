"""Domain targets: 'which AI answers cite this domain?' — the tracking loop."""
import sys
from collections import Counter
sys.path.insert(0, '.')
from src.tools.dataforseo import _post, _run

async def probe(domain, scope, limit=20):
    return await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [{
        "target": [{"domain": domain, "search_filter": "include", "search_scope": scope}],
        "location_code": 2840, "language_code": "en", "limit": limit,
    }])

for dom in ("www.evidentlyai.com", "stripe.com", "productpirates.club"):
    for scope in (["sources"], ["any"]):
        try:
            d = _run(probe(dom, scope))
            t = (d.get("tasks") or [{}])[0]
            if t.get("status_code") != 20000:
                print(f"  {dom:<22}{str(scope):<12} err {t.get('status_code')}: "
                      f"{str(t.get('status_message'))[:80]}")
                continue
            res = (t.get("result") or [{}])[0]
            items = res.get("items") or []
            vol = sum(i.get("ai_search_volume") or 0 for i in items)
            print(f"  {dom:<22}{str(scope):<12} total={res.get('total_count'):>5} "
                  f"items={len(items):>3} ai_vol_sum={vol}")
            for i in items[:3]:
                srcs = [s.get('domain') for s in (i.get('sources') or [])][:3]
                print(f"        cited for {str(i.get('question'))[:40]!r} alongside {srcs}")
        except Exception as e:
            print(f"  {dom:<22}{str(scope):<12} ERR {str(e)[:80]}")
