"""The full GEO node chain on the real topics, offline from the chat layer."""
import sys, time
sys.path.insert(0, '.')
from src import market as market_mod, pipeline_recorder as rec, runs
from src.tools.geo_demand import run_geo_demand

RID = "diag-geo-live"
runs.save_run(RID, {"id": RID, "project": "diag", "title": "geo", "status": "running", "stages": []})
with rec.use_run(RID):
    market_mod.reset(RID)
    market_mod.confirm_market("US", "en", run_id=RID)
    t = time.time()
    res = run_geo_demand(
        ["agentic commerce", "knowledge graphs", "llm evaluation", "forward deployed engineer"],
        max_question_terms=3,
    )
print(f"\n{time.time()-t:.1f}s  success={res.get('success')}  steps={res.get('steps')}\n")
for b in res.get("brief", []):
    m = b["metrics"]
    print(f"  {b['topic'].upper()}")
    print(f"     google volume {m['search_volume']}/mo | AI questions {m['ai_questions_found']} "
          f"| AI volume {m['ai_search_volume']}")
    print(f"     cited authority {m['weakest_cited_authority']}-{m['strongest_cited_authority']}")
    print(f"     -> {b['can_you_displace_them']}")
    if b["niche_sites_already_cited"]:
        print(f"     niche already cited: "
              f"{[(d['domain'], d['authority_rank']) for d in b['niche_sites_already_cited'][:3]]}")
    print(f"     people also ask: {b['questions_people_ask'][:3]}")
    print()
print("skipped (no demand):", res.get("skipped_no_demand"))
