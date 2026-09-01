"""Does the lean prompt make selection fast enough to stop being fragile?

The failure was never reproduced: the same input succeeds. But it took 239s
against a node the live run gave 281s before moving on — so the question is not
"what raised" but "why is it that close to the edge".
"""
import json, sys, time
sys.path.insert(0, '.')
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.tools.score_clusters import score_clusters
from src.tools.select_clusters import select_clusters, _for_selection

run = json.load(open("../agent-memory/runs/chat-20260901T144839-623a88.json", encoding="utf-8"))
st = {s["id"]: s.get("artifact", {}) for s in run["stages"]}
cl = st["clusters"]
clusters = (cl.get("clusters") or []) + (cl.get("discarded") or [])
scored = score_clusters({"clusters": clusters}, keywords=st.get("keywords", {}).get("keywords", []))

BIZ = ("Product Pirates - an AI community of practice for product people who want "
       "hands-on experience building AI products.")

print(f"lean prompt: {len(json.dumps(_for_selection(scored), ensure_ascii=False)):,} chars")
t = time.time()
res = select_clusters(scored, max_select=4, business_description=BIZ)
el = time.time() - t
print(f"select_clusters -> {el:.1f}s  success={res.get('success')}  (was 239.4s on the fat prompt)")
if res.get("success"):
    sel = res["selection"]
    print(f"  selected: {sel['selected']}")
    for r in (sel.get("selected_reasons") or [])[:4]:
        print(f"    + {r['cluster_name']}: {str(r['reason'])[:82]}")
    for d in (sel.get("discarded") or [])[:3]:
        print(f"    - {d.get('cluster_name')}: {str(d.get('reason'))[:76]}")
else:
    print(f"  ERROR: {res.get('error')}")
