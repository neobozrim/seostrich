"""What does search_scope actually change: the matching, or the payload?"""
import sys, json
from collections import Counter
sys.path.insert(0, '.')
from src.tools.dataforseo import _post, _run

TOPIC = "llm evaluation"

def probe(scope, limit=20):
    async def _inner():
        return await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [{
            "target": [{"keyword": TOPIC, "search_filter": "include",
                        "search_scope": scope, "match_type": "word_match"}],
            "location_code": 2840, "language_code": "en", "limit": limit,
        }])
    try:
        data = _run(_inner())
        t = (data.get("tasks") or [{}])[0]
        if t.get("status_code") != 20000:
            return None, f"error {t.get('status_code')}: {str(t.get('status_message'))[:70]}"
        res = (t.get("result") or [{}])[0]
        return res, None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"

for scope in (["question"], ["answer"], ["sources"], ["question", "answer", "sources"]):
    res, err = probe(scope)
    label = str(scope)
    if err:
        print(f"  {label:<36} {err}")
        continue
    items = res.get("items") or []
    doms = Counter(s.get("domain") for i in items for s in (i.get("sources") or []) if s.get("domain"))
    qs = [(i.get("question") or "")[:44] for i in items[:3]]
    kw_in_q = sum(1 for i in items if TOPIC.split()[0] in (i.get("question") or "").lower())
    print(f"  {label:<36} total={res.get('total_count'):>6} items={len(items):>3} "
          f"distinct_domains={len(doms):>3}  kw-in-question={kw_in_q}/{len(items)}")
    for q in qs:
        print(f"        q: {q!r}")
    if doms:
        print(f"        top domains: {[d for d,_ in doms.most_common(4)]}")
