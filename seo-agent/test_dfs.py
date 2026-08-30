"""Pull full Bulgarian theatre keyword universe for Neobozrim."""
import sys, os, json
print("Starting...", flush=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.tools import dataforseo

KEYWORDS = [
    "театър",
    "театър София",
    "моноспектакъл",
    "авторски театър",
    "поетичен театър",
    "билети театър",
    "билети за театър София",
    "театрална пиеса",
    "представление",
    "актьор",
    "spoken word",
    "поезия на сцена",
    "театър програма",
    "театрално изкуство",
    "театър сълза и смях",
    "народен театър",
    "пиеса",
    "драма",
    "комедия театър",
    "мюзикъл",
    "театрален фестивал",
    "независим театър",
    "алтернативен театър",
    "експериментален театър",
    "solo performance",
    "theatre Sofia",
]

print(f"Pulling keyword data for {len(KEYWORDS)} terms (Bulgarian market)...", flush=True)
results = dataforseo.keyword_overview(KEYWORDS, location_code=2100, language_code="bg")

print(f"\nGot {len(results)} results:\n", flush=True)
# Sort by volume
results.sort(key=lambda x: x.get("volume", 0), reverse=True)

for kw in results:
    vol = kw.get('volume') or 0
    diff = kw.get('difficulty') or 0
    cpc = kw.get('cpc') or 0
    print(f"  {kw['keyword']:40s} vol={vol:>6}  diff={diff:>3}  cpc={cpc:.2f}  intent={kw.get('intent','?')}", flush=True)

# Save to file
output_path = os.path.join("..", "agent-memory", "artefacts", "neobozrim-bulgarian-keywords.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved to: {output_path}", flush=True)
