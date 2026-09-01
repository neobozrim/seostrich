"""What do the GEO signals actually contain? Platforms, volumes, who is cited."""
import sys
from collections import Counter
sys.path.insert(0, '.')
from src.tools.dataforseo import ai_mentions_keywords, keyword_overview

TOPIC = "agentic commerce"
rows = ai_mentions_keywords([TOPIC], location_code=2840, language_code="en", limit=100)
kw = keyword_overview([TOPIC], location_code=2840, language_code="en")

print(f"classic Google search volume for {TOPIC!r}: {kw[0]['volume'] if kw else 'n/a'}/mo")
print(f"AI-engine rows returned: {len(rows)}")
print(f"platforms: {dict(Counter(r['platform'] for r in rows))}")
print(f"models: {dict(Counter(r.get('model_name') or '-' for r in rows))}")
print(f"total ai_search_volume across rows: {sum(r['ai_search_volume'] for r in rows)}")
print(f"rows WITH an answer: {sum(1 for r in rows if r['has_answer'])} / {len(rows)}")
print(f"rows WITH cited sources: {sum(1 for r in rows if r['sources'])} / {len(rows)}")

doms = Counter(s['domain'] for r in rows for s in r['sources'] if s.get('domain'))
print(f"\ncited domains ({len(doms)} distinct):")
for d, n in doms.most_common(14):
    print(f"   {n:>3}x  {d}")

print("\nsample rows:")
for r in rows[:5]:
    print(f"   [{r['platform']:<8}] {r['question'][:52]!r} ai_vol={r['ai_search_volume']} "
          f"answered={r['has_answer']} sources={[s['domain'] for s in r['sources']][:3]}")
