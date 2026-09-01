"""Do the mechanical-ish nodes lose quality on the fast model?

Latency is the demo constraint (a 9-minute run is not a 3-minute video), and
the fast model was 5.8x quicker on clustering with equal output. Check whether
that holds for seed extraction, where quality actually matters: the seeds
decide what the whole strategy is about.
"""
import sys, time, json
sys.path.insert(0, '.')
from pathlib import Path
from src import llm
from src.config import settings
from src.tools.extract_seeds import SYSTEM_PROMPT

brief = Path("pp_input.txt").read_text(encoding="utf-8")
user_msg = f"""Business Description:
{brief}

Site Description:
productpirates.club

Competitor URLs:

Target search language: en

Extract keyword seeds for SEO research."""

for model in (settings.qwen_model, settings.qwen_model_fast):
    t = time.time()
    try:
        r = llm.chat(user_msg, system=SYSTEM_PROMPT, temperature=0.3,
                     max_tokens=800, model=model)
        seeds = llm.parse_json_response(r)
        elapsed = time.time() - t
        allseeds = []
        for k in ("business_seeds", "site_seeds", "competitor_seeds"):
            allseeds += seeds.get(k) or []
        print(f"\n  {model:16} {elapsed:6.1f}s  {len(allseeds)} seeds")
        for k in ("business_seeds", "site_seeds", "competitor_seeds"):
            print(f"      {k:18} {seeds.get(k)}")
    except Exception as e:
        print(f"\n  {model:16} ERR {type(e).__name__}: {str(e)[:100]}")
