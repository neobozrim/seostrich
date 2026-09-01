"""Evaluate SERP verification on the real Product Pirates clusters.

The question: does Google actually treat the LLM's thematic clusters as one
intent? If two clusters share results, one page serves both and keeping them
apart splits the effort. If they do not, merging them produces a page that
ranks for neither.
"""
import json, sys, time
sys.path.insert(0, '.')
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.tools.serp_verify import verify_clusters, apply_merges, _candidate_pairs

run = json.load(open("../agent-memory/runs/chat-20260901T144839-623a88.json", encoding="utf-8"))
st = {s["id"]: s.get("artifact", {}) for s in run["stages"]}
cl = st["clusters"]
clusters = (cl.get("clusters") or []) + (cl.get("discarded") or [])
heads = [c.get("head_term") or c.get("cluster_name") or c.get("name") for c in clusters]

print(f"{len(clusters)} clusters proposed thematically:")
for h in heads:
    print(f"    {h}")
print(f"\ncandidate pairs (share vocabulary): {len(_candidate_pairs([h or '' for h in heads]))}")

t = time.time()
v = verify_clusters(clusters, 2840, "en", max_calls=8)
print(f"\nverified in {time.time()-t:.1f}s using {v['checked']} SERP calls "
      f"({v.get('pairs_considered')} pairs considered)\n")

print("MERGE — Google returns the same results:")
for m in v["merges"]:
    print(f"  {m['a']}  +  {m['b']}   overlap {m['overlap']}")
    for u in m["shared_results"][:3]:
        print(f"      shared: {u[:78]}")
if not v["merges"]:
    print("  (none)")

print("\nKEEP SEPARATE — different results despite similar words:")
for k in v["kept_separate"][:8]:
    print(f"  {k['a']}  vs  {k['b']}   overlap {k['overlap']}")
    print(f"      {k['why']}")

merged = apply_merges(clusters, v)
print(f"\n{len(clusters)} clusters -> {len(merged)} after merging")
for c in merged:
    if c.get("merged_from"):
        print(f"    MERGED: {' + '.join(c['merged_from'])}  ({len(c['keywords'])} keywords)")
