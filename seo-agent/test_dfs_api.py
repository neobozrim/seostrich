"""Check DataForSEO response structure for working endpoints."""
import os, sys, base64, httpx, json

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv('C:/Users/Yavor/Downloads/qwen/.env')

login = os.getenv('DATAFORSEO_LOGIN', '')
pw = os.getenv('DATAFORSEO_PASSWORD', '')
auth = base64.b64encode(f'{login}:{pw}'.encode()).decode()
headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}

# Get related keywords with full response
resp = httpx.post(
    'https://api.dataforseo.com/v3/dataforseo_labs/google/related_keywords/live',
    headers=headers,
    content=json.dumps([{
        'keyword': 'product manager AI tools',
        'location_code': 2840,
        'language_code': 'en',
        'limit': 10
    }]),
    timeout=30
)

data = resp.json()
items = data['tasks'][0]['result'][0]['items']

print(f"Total items: {len(items)}")
print(f"\nFirst item keys: {list(items[0].keys())}")
print(f"\nFirst item full:")
print(json.dumps(items[0], indent=2, default=str)[:2000])

# Get keyword suggestions too
print("\n\n=== KEYWORD SUGGESTIONS ===")
resp2 = httpx.post(
    'https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_suggestions/live',
    headers=headers,
    content=json.dumps([{
        'keyword': 'product manager AI tools',
        'location_code': 2840,
        'language_code': 'en',
        'limit': 10
    }]),
    timeout=30
)

data2 = resp2.json()
items2 = data2['tasks'][0]['result'][0]['items']

print(f"Total items: {len(items2)}")
print(f"\nFirst item keys: {list(items2[0].keys())}")
print(f"\nFirst item full:")
print(json.dumps(items2[0], indent=2, default=str)[:2000])
