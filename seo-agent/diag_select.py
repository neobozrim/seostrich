"""Why did select_clusters fail on the Product Pirates run?"""
import json, sys, time
sys.path.insert(0, '.')
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.tools.score_clusters import score_clusters
from src.tools import select_clusters as sc

run = json.load(open("../agent-memory/runs/chat-20260901T144839-623a88.json", encoding="utf-8"))
stages = {s["id"]: s.get("artifact", {}) for s in run["stages"]}
cl = stages["clusters"]
clusters = (cl.get("clusters") or []) + (cl.get("discarded") or [])
kws = stages.get("keywords", {}).get("keywords", [])
print(f"{len(clusters)} clusters, {len(kws)} keywords in the universe")

scored = score_clusters({"clusters": clusters}, keywords=kws)
payload = json.dumps(scored, ensure_ascii=False)
print(f"scored payload handed to select_clusters: {len(payload):,} chars (~{len(payload)//4:,} tokens)")

BIZ = ("Product Pirates - an AI community of practice for product people who want "
       "hands-on experience building AI products.")
t = time.time()
res = sc.select_clusters(scored, max_select=4, business_description=BIZ)
print(f"\nselect_clusters -> {time.time()-t:.1f}s success={res.get('success')}")
if not res.get("success"):
    print(f"  ERROR: {res.get('error')}")
else:
    sel = res["selection"]
    print(f"  selected: {sel['selected']}")
    print(f"  reasons : {len(sel.get('selected_reasons') or [])}")
    print(f"  discarded: {len(sel.get('discarded') or [])}")
