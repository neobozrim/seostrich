import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from src.tools.dataforseo import keyword_overview

terms = ['театър', 'театър софия програма', 'театър билети', 'съвременен театър', 'авторски театър', 'поетичен театър']
results = keyword_overview(terms, location_code=2100, language_code='bg')

with open('../agent-memory/artefacts/additional-theatre-keywords.json', 'w', encoding='utf-8') as f:
    import json
    json.dump(results, f, indent=2, ensure_ascii=False)

# Also print to console
for kw in results:
    vol = kw.get('volume') or 0
    diff = kw.get('difficulty') or 0
    print(f"{kw['keyword']:40s} vol={vol:>6}  diff={diff:>3}")
