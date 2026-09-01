"""Which match_type / search_scope gives questions actually about the topic?

word_match returned "aviation in ww1" for "forward deployed engineer" — it is
matching single words, which makes the citability data noise.
"""
import sys, json
sys.path.insert(0, '.')
from src.tools.dataforseo import _post, _run

TOPIC = "agentic commerce"

def probe(match_type, scope):
    async def _inner():
        return await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [{
            "target": [{"keyword": TOPIC, "search_filter": "include",
                        "search_scope": scope, "match_type": match_type}],
            "location_code": 2840, "language_code": "en", "limit": 10,
        }])
    try:
        data = _run(_inner())
        t = (data.get("tasks") or [{}])[0]
        if t.get("status_code") != 20000:
            return f"task error {t.get('status_code')}: {str(t.get('status_message'))[:60]}", []
        res = (t.get("result") or [{}])[0]
        items = res.get("items") or []
        return f"total={res.get('total_count')} items={len(items)}", [
            (i.get("question") or "")[:52] for i in items[:4]
        ]
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:60]}", []

for mt in ("word_match", "phrase_match", "exact_match"):
    for scope in (["any"], ["question"]):
        summary, qs = probe(mt, scope)
        print(f"  {mt:<13} scope={str(scope):<12} {summary}")
        for q in qs:
            print(f"        {q!r}")
