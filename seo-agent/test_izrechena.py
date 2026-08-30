import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from src.tools import dataforseo

print('=== Checking "изречена поезия" (Bulgarian) ===', flush=True)
try:
    results = dataforseo.keyword_overview(
        ['изречена поезия', 'изречена поезия театър', 'spoken word poetry', 'хубав театър комедия', 'независим театър'],
        location_code=2100,
        language_code='bg'
    )
    print(f'Got {len(results)} results:', flush=True)
    for kw in results:
        vol = kw.get('volume') or 0
        diff = kw.get('difficulty') or 0
        print(f'  {kw["keyword"]:40s} vol={vol:>6}  diff={diff:>3}', flush=True)
    if not results:
        print('  No results - term not in DataForSEO database', flush=True)
except Exception as e:
    print(f'Error: {e}', flush=True)

print('\n=== Checking related terms ===', flush=True)
try:
    related = dataforseo.related_keywords('изречена поезия', location_code=2100, language_code='bg', limit=20)
    print(f'Got {len(related)} related keywords:', flush=True)
    for kw in related[:10]:
        vol = kw.get('volume') or 0
        diff = kw.get('difficulty') or 0
        print(f'  {kw["keyword"]:40s} vol={vol:>6}  diff={diff:>3}', flush=True)
except Exception as e:
    print(f'Error: {e}', flush=True)

print('\n=== Checking international terms (English, Denmark) ===', flush=True)
try:
    results_en = dataforseo.keyword_overview(
        ['spoken word theatre', 'monodrama', 'solo performance', 'poetry performance'],
        location_code=2080,  # Denmark
        language_code='en'
    )
    print(f'Got {len(results_en)} results:', flush=True)
    for kw in results_en:
        vol = kw.get('volume') or 0
        diff = kw.get('difficulty') or 0
        print(f'  {kw["keyword"]:40s} vol={vol:>6}  diff={diff:>3}', flush=True)
except Exception as e:
    print(f'Error: {e}', flush=True)
