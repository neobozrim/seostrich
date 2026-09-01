"""Can we grade the cited domains by authority in ONE call?

The valuable GEO signal is not "is this answered" (Google AI Overview answers
almost everything) but WHO it cites: Mastercard and McKinsey are not
displaceable, a niche site is.
"""
import sys, json
sys.path.insert(0, '.')
from src.tools.dataforseo import _post, _run

DOMAINS = ["www.mastercard.com", "stripe.com", "www.agenticcommerce.dev",
           "www.digitalcommerce360.com", "www.pymnts.com", "productpirates.club"]

async def _inner():
    return await _post("/v3/backlinks/bulk_ranks/live", [{"targets": DOMAINS}])

try:
    data = _run(_inner())
    t = (data.get("tasks") or [{}])[0]
    print(f"status={t.get('status_code')} {str(t.get('status_message'))[:70]}")
    res = (t.get("result") or [{}])[0]
    items = res.get("items") or []
    print(f"{len(items)} graded in ONE call:")
    for i in items:
        print(f"   rank {str(i.get('rank')):>5}   {i.get('target')}")
except Exception as e:
    print(f"ERR {type(e).__name__}: {str(e)[:160]}")
