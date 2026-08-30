"""Pull related keyword suggestions for Neobozrim's Bulgarian theatre market."""
import sys, os, json
print("Starting...", flush=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.tools import dataforseo

SEEDS = [
    "моноспектакъл",
    "авторски театър",
    "театър софия",
    "билети за театър",
    "spoken word",
    "поетичен театър",
]

all_results = []

for seed in SEEDS:
    print(f"\n--- Related keywords for: {seed} ---", flush=True)
    try:
        results = dataforseo.related_keywords(seed, location_code=2100, language_code="bg", limit=30)
        print(f"  Got {len(results)} results", flush=True)
        for kw in results[:10]:
            vol = kw.get('volume') or 0
            diff = kw.get('difficulty') or 0
            print(f"    {kw['keyword']:45s} vol={vol:>6}  diff={diff:>3}", flush=True)
        all_results.extend(results)
    except Exception as e:
        print(f"  Error: {e}", flush=True)

print(f"\n--- Keyword suggestions ---", flush=True)
for seed in SEEDS[:3]:
    try:
        results = dataforseo.keyword_suggestions(seed, location_code=2100, language_code="bg", limit=20)
        print(f"  Suggestions for '{seed}': {len(results)}", flush=True)
        for kw in results[:10]:
            vol = kw.get('volume') or 0
            diff = kw.get('difficulty') or 0
            print(f"    {kw['keyword']:45s} vol={vol:>6}  diff={diff:>3}", flush=True)
        all_results.extend(results)
    except Exception as e:
        print(f"  Error: {e}", flush=True)

# Deduplicate by keyword
seen = set()
deduped = []
for kw in all_results:
    key = kw.get("keyword", "").lower()
    if key and key not in seen:
        seen.add(key)
        deduped.append(kw)

deduped.sort(key=lambda x: x.get("volume") or 0, reverse=True)

output_path = os.path.join("..", "agent-memory", "artefacts", "neobozrim-related-keywords.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(deduped, f, indent=2, ensure_ascii=False)

print(f"\n=== {len(deduped)} unique related keywords saved to {output_path} ===", flush=True)
