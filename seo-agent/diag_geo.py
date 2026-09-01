"""Why did AI citability return zero for every topic?"""
import sys, json
sys.path.insert(0, '.')
from src.tools.dataforseo import ai_mentions_keywords, _post, _run, _normalize

TOPICS = ["agentic commerce", "knowledge graphs", "llm evaluation"]

print("1. via the wrapper")
try:
    r = ai_mentions_keywords(TOPICS, location_code=2840, language_code="en")
    print(f"   returned {len(r)} items")
    for i in r[:3]:
        print("   ", json.dumps(i, ensure_ascii=False)[:200])
except Exception as e:
    print(f"   ERR {type(e).__name__}: {e}")

print("\n2. raw response, to see what the API actually says")
async def _inner():
    return await _post("/v3/ai_optimization/llm_mentions/search_mentions/live", [{
        "target": [{"keyword": k, "search_filter": "include",
                    "search_scope": ["any"], "match_type": "word_match"} for k in TOPICS],
        "location_code": 2840, "language_code": "en", "limit": 20,
    }])
try:
    data = _run(_inner())
    print(f"   status_code={data.get('status_code')} status_message={data.get('status_message')}")
    for t in data.get("tasks") or []:
        print(f"   task: code={t.get('status_code')} msg={t.get('status_message')!r}")
        res = t.get("result")
        print(f"   result type={type(res).__name__} len={len(res) if isinstance(res,list) else 'n/a'}")
        if isinstance(res, list) and res:
            r0 = res[0]
            print(f"   result[0] keys: {list(r0)[:12]}")
            print(f"   items: {len(r0.get('items') or [])}")
            print("   raw result[0]:", json.dumps(r0, ensure_ascii=False)[:600])
except Exception as e:
    print(f"   ERR {type(e).__name__}: {e}")
