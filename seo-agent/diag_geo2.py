"""Does batching keywords into one search_mentions call AND them or OR them?

The wrapper's docstring claims "One call covers up to 10 head terms", which is
only a saving if the targets are unioned. If they intersect, batching silently
returns nothing.
"""
import sys, time
sys.path.insert(0, '.')
from src.tools.dataforseo import ai_mentions_keywords

TOPICS = ["agentic commerce", "knowledge graphs", "llm evaluation", "forward deployed engineer"]

print("individually:")
singles = {}
for t in TOPICS:
    try:
        r = ai_mentions_keywords([t], location_code=2840, language_code="en")
        singles[t] = len(r)
        print(f"  {t:<28} {len(r):>3} answers")
        for i in r[:2]:
            print(f"       [{i.get('platform')}] {str(i.get('question'))[:66]}")
    except Exception as e:
        print(f"  {t:<28} ERR {e}")

print("\nbatched:")
for n in (2, 3, 4):
    try:
        r = ai_mentions_keywords(TOPICS[:n], location_code=2840, language_code="en")
        print(f"  first {n} topics together -> {len(r):>3} answers "
              f"(sum of singles = {sum(singles.get(t,0) for t in TOPICS[:n])})")
    except Exception as e:
        print(f"  first {n} -> ERR {e}")
