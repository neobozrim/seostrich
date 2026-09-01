import sys, time
sys.path.insert(0, '.')
from src import llm
from src.config import settings

msgs = [{"role": "user", "content": "In two sentences, why is keyword clustering useful?"}]
print(f"model={settings.qwen_model}")

print("\n-- non-streaming --")
r = llm.chat(msgs, temperature=0.3, max_tokens=300)
print(f"   content={r.get('content','')[:120]!r}")

print("\n-- streaming --")
deltas, final = [], None
t = time.time()
for ev in llm.chat_stream(msgs, temperature=0.3, max_tokens=300):
    if ev["type"] == "delta":
        deltas.append(ev["content"])
        if len(deltas) == 1:
            print(f"   first delta at {time.time()-t:.1f}s: {ev['content']!r}")
    else:
        final = ev
print(f"   {len(deltas)} deltas, joined len={len(''.join(deltas))}")
print(f"   final content len={len(final['content'])} tool_calls={final['tool_calls']}")

print("\n-- raw SDK stream: what fields actually carry text? --")
from openai import OpenAI
c = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url, timeout=120, max_retries=0)
seen = {}
n = 0
for ev in c.chat.completions.create(model=settings.qwen_model, messages=msgs,
                                    max_tokens=300, stream=True):
    n += 1
    if not ev.choices:
        seen["no_choices"] = seen.get("no_choices", 0) + 1
        continue
    d = ev.choices[0].delta
    for f in ("content", "reasoning_content"):
        v = getattr(d, f, None)
        if v:
            seen[f] = seen.get(f, 0) + 1
    extra = getattr(d, "model_extra", None) or {}
    for k, v in extra.items():
        if v:
            seen[f"extra:{k}"] = seen.get(f"extra:{k}", 0) + 1
print(f"   {n} chunks; fields carrying data: {seen}")
