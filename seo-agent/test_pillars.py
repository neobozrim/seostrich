import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.tools import dataforseo

terms = [
    'хубав театър комедия',
    'независим театър',
    'моноспектакъл',
    'театър софия',
    'театрална пиеса',
    'представление софия',
    'билети за театър софия',
    'spoken word',
    'spoken word poetry',
    'моноспектакъл софия',
    'авторски театър',
    'поетичен театър',
]

print('=== Full keyword check for all pillar terms ===', flush=True)
results = dataforseo.keyword_overview(terms, location_code=2100, language_code='bg')
print(f'Got {len(results)} results:\n', flush=True)
results.sort(key=lambda x: x.get('volume') or 0, reverse=True)
for kw in results:
    vol = kw.get('volume') or 0
    diff = kw.get('difficulty') or 0
    cpc = kw.get('cpc') or 0
    intent = kw.get('intent') or '?'
    print(f'  {kw["keyword"]:40s} vol={vol:>6}  diff={diff:>3}  cpc={cpc:.2f}  intent={intent}', flush=True)
