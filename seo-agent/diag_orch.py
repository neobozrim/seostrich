import sys, time, json
sys.path.insert(0, '.')
from src import llm, orchestrator as orch
from pathlib import Path

msg = Path("pp_input.txt").read_text(encoding="utf-8")
tools = [t for t in orch.run_orchestrator_stream.__globals__.get("_x", [])]  # placeholder

# rebuild exactly what the orchestrator sends
from src import flows
orchestrator_tools = [{
    "type": "function",
    "function": {
        "name": "seo_agent",
        "description": "Route a task to the SEO specialist agent.",
        "parameters": {"type": "object", "properties": {
            "flow": {"type": "string", "enum": list(flows.REGISTRY) + ["other"]},
            "task": {"type": "string"}, "context": {"type": "string"}},
            "required": ["flow", "task"]}}}]

print("STREAMING with tools:")
t = time.time(); deltas = []; final = None
for ev in llm.chat_stream([{"role": "user", "content": msg}],
                          system=orch.ORCHESTRATOR_SYSTEM_PROMPT,
                          tools=orchestrator_tools, temperature=0.3):
    if ev["type"] == "delta":
        deltas.append(ev["content"])
    else:
        final = ev
print(f"  {time.time()-t:.1f}s  deltas={len(deltas)}  content_len={len(final['content'])}  "
      f"tool_calls={[(c['name'], c['arguments'][:60]) for c in final['tool_calls']]}")

print("\nNON-STREAMING, same inputs:")
t = time.time()
r = llm.chat([{"role": "user", "content": msg}], system=orch.ORCHESTRATOR_SYSTEM_PROMPT,
             tools=orchestrator_tools, temperature=0.3)
print(f"  {time.time()-t:.1f}s  content_len={len(r.get('content',''))}  "
      f"tool_calls={[(c['name'], c['arguments'][:60]) for c in r.get('tool_calls',[])]}")
print(f"  content: {r.get('content','')[:200]!r}")
