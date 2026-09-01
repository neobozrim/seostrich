"""
Orchestrator Layer - Conversation routing and agent coordination.

The orchestrator is the "front desk" that:
- Handles user conversation
- Identifies what type of work is needed
- Routes to appropriate agent(s)
- Maintains conversation state across agents

It doesn't know domain details, just recognizes agent capabilities.
"""

import contextvars
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import flows
from . import llm
from . import memory
from . import pipeline_recorder
from . import session as session_store
from .agent import run_agent
from .brand_agent import run_brand_agent
from .builder_agent import run_builder_agent
from .monitoring_agent import run_monitoring_agent


# Short user replies that approve continuing a budget-stopped run.
_CONTINUATION_WORDS = {
    "continue", "proceed", "go on", "keep going", "yes", "yes, continue",
    "да", "продължи",
}


class StopRequested(Exception):
    """Raised inside a stream when the user asked to stop it."""


# Cooperative stop: /api/chat/stop sets the flag for a session id; the
# stream checks it between yields and run_agent checks it between rounds.
_stop_flags: dict[str, bool] = {}
_stop_lock = threading.Lock()


def request_stop(session_id: str) -> bool:
    """Ask a live stream to stop. False when no stream is armed for this session."""
    with _stop_lock:
        if session_id in _stop_flags:
            _stop_flags[session_id] = True
            return True
        return False


def _check_stop(sid: str | None) -> None:
    if not sid:
        return
    with _stop_lock:
        if _stop_flags.get(sid):
            raise StopRequested()


ORCHESTRATOR_SYSTEM_PROMPT = """You are the front desk of an SEO agent. You do not do
SEO work yourself — you work out which FLOW the user needs, make sure you have what that
flow requires, and then hand off.

**Flows the SEO agent can run**

1. `keyword_strategy` — Content strategy from scratch.
   Needs: what the business does (in the user's words) AND the target country + language.
   Runs: seeds -> keyword universe -> clusters -> validation gate -> selection ->
   AI-citability -> content pillars.

2. `geo_demand` — AI visibility (GEO).
   Needs: the topics to investigate AND the target country + language.
   Runs: how AI engines answer these topics today, who they cite, what share is open,
   and the real questions people ask.

3. `other` — anything else (technical audits, GSC analysis, indexing, drafting).

**The one rule you must not break: never guess the market.**
Every research flow needs a target COUNTRY and a target LANGUAGE, and both must have been
stated by the user. You may not infer either one:
- Not from the domain or its TLD. A .bg site does not mean the business targets Bulgaria.
- Not from the site's content, the business name, or the language the user is writing in.
  Someone can describe their business to you in one language and sell in another.
If you do not have both, ASK — one short, friendly question — and do NOT call seo_agent yet.
Ask it as "which country do your customers search from, and in which language?", because
where the business is based is not the same as the market it sells into.

Getting this wrong is expensive and obvious: it sends the whole pipeline into the wrong
market and returns confident, well-formatted keywords from an unrelated industry.

**How to work**
- Understand the goal, name the flow, check the flow's requirements are met.
- Missing something? Ask for it. One question at a time. Do not route a half-specified job.
- Have everything? Call `seo_agent` with the flow id, a clear task, and a context string
  that includes the country and language the user gave you.
- When the agent returns, present its results plainly and ask what they want to adjust.
- Don't call an agent for a greeting or a general question — just answer.

**Other specialists** (route only when clearly asked):
- `brand_agent` — brand identity, voice, naming, visual system.
- `builder_agent` — code generation, asset creation, building sites/apps.
- `monitoring_agent` — performance tracking, traffic-drop diagnosis, indexing health,
  rank tracking, freshness alerts.

**Examples**

User: "I have a new blog and want to grow traffic"
-> Ask what the business does, then ask which country + language to target.
-> Only once you have both: seo_agent(flow="keyword_strategy", task="Build a content
   strategy", context="<business> ... Target market: United States, English")

User: "productpirates.club — an AI community for product people, I'm in Bulgaria"
-> Do NOT assume Bulgaria/Bulgarian. Ask: "Which country do your members search from,
   and in which language should the content be?"

User: "What do AI engines say about agentic commerce?"
-> Ask country + language, then seo_agent(flow="geo_demand", ...)

User: "Audit my site"
-> Ask for the URL, then seo_agent(flow="other", task="Technical SEO audit", context=URL)
"""

AGENT_REGISTRY = {
    "seo_agent": {
        "description": "SEO specialist - keyword research, content strategy, technical audits, indexing, analytics",
        "handler": run_agent,
    },
    "brand_agent": {
        "description": "Brand identity specialist - brand discovery, voice/typography/color, naming, brand profiles",
        "handler": run_brand_agent,
    },
    "builder_agent": {
        "description": "Implementation specialist - code generation, asset creation, 3-tier verification",
        "handler": run_builder_agent,
    },
    "monitoring_agent": {
        "description": "SEO monitoring specialist - performance tracking, traffic drop diagnosis, indexing health, keyword rankings, freshness alerts",
        "handler": run_monitoring_agent,
    }
}


def run_orchestrator(
    initial_message: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run the orchestrator conversation layer.
    
    Args:
        initial_message: Optional first message from user
        session_id: Optional session ID to resume
        
    Returns:
        Session data with all messages and agent calls
    """
    from .agent import TOOL_CALLABLES  # Import here to avoid circular dependency
    
    # Create orchestrator-specific tool definitions
    orchestrator_tools = [
        {
            "type": "function",
            "function": {
                "name": "seo_agent",
                "description": "Route a task to the SEO specialist agent. Use this when the user needs SEO help.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "What the SEO agent should do (e.g., 'Create SEO strategy', 'Technical audit')"
                        },
                        "context": {
                            "type": "string",
                            "description": "Relevant context: business info, goals, constraints, URLs, etc."
                        }
                    },
                    "required": ["task"]
                }
            }
        }
    ]
    
    # Initialize session
    sid = session_id or session_store.new_session_id()
    if session_id:
        session_data = session_store.load_session(session_id)
    else:
        session_data = {
            "session_id": sid,
            "created_at": datetime.utcnow().isoformat(),
            "messages": [],
            "agent_calls": [],
            "orchestrator_tool_results": [],
        }
    
    messages = session_data["messages"]
    
    # Add orchestrator tool to callables
    def call_seo_agent(task: str, context: str = "") -> dict:
        """Call the SEO agent with a task and context."""
        print(f"\n[Routing to SEO Agent]")
        print(f"  Task: {task}")
        if context:
            print(f"  Context: {context[:200]}...")
        
        # Combine task and context into a message for the SEO agent
        agent_message = f"{task}\n\n{context}".strip()

        # Run the SEO agent
        result = run_agent(agent_message)

        # Extract the assistant's response
        assistant_messages = [m for m in result["messages"] if m.get("role") == "assistant" and m.get("content")]
        agent_response = assistant_messages[-1]["content"] if assistant_messages else "No response from SEO agent"

        # Store agent call in session
        session_data["agent_calls"].append({
            "task": task,
            "context": context,
            "agent_session_id": result["session_id"],
            "tool_calls": len(result["tool_results"]),
            "response": agent_response,
        })

        return {
            "status": "success",
            "agent_session_id": result["session_id"],
            "tool_calls_made": len(result["tool_results"]),
            "response": agent_response,
        }


def run_orchestrator_stream(
    initial_message: str,
    session_id: Optional[str] = None,
):
    """
    Run the orchestrator as a streaming generator.
    Yields events as they happen: text chunks, tool calls, tool results.

    Yields:
        dict with 'type' field: 'text', 'tool_start', 'tool_end', 'done', 'error'
    """
    from .agent import TOOL_CALLABLES

    # Create orchestrator-specific tool definitions
    orchestrator_tools = [
        {
            "type": "function",
            "function": {
                "name": "seo_agent",
                "description": (
                    "Route a task to the SEO specialist agent. Pick the FLOW that "
                    "matches what the user wants. Do not call this until every "
                    "required input for that flow has been stated by the user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flow": {
                            "type": "string",
                            "enum": list(flows.REGISTRY) + ["other"],
                            "description": (
                                "keyword_strategy = build a content strategy from "
                                "scratch; geo_demand = AI visibility / what AI "
                                "engines answer and cite; other = anything else."
                            ),
                        },
                        "task": {"type": "string"},
                        "context": {
                            "type": "string",
                            "description": (
                                "Everything the flow needs, including the target "
                                "country and language the user stated."
                            ),
                        },
                    },
                    "required": ["flow", "task"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "brand_agent",
                "description": "Route a task to the Brand identity agent. Use for brand creation, rebranding, voice/tone/visual identity, naming.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "context": {"type": "string"}
                    },
                    "required": ["task"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "builder_agent",
                "description": "Route a task to the Builder agent. Use for code generation, asset creation (wordmarks/icons/photos), building websites/apps with 3-tier verification.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "context": {"type": "string"}
                    },
                    "required": ["task"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "monitoring_agent",
                "description": "Route a task to the Monitoring agent. Use for performance tracking, traffic drop diagnosis, indexing health checks, keyword ranking monitoring, content freshness alerts, and monitoring reports.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "context": {"type": "string"}
                    },
                    "required": ["task"]
                }
            }
        }
    ]

    # Load or create session
    if session_id:
        sid = session_id
        session_data = session_store.load_session(session_id)
        if session_data is None:
            session_data = {
                "session_id": session_id,
                "messages": [],
                "agent_calls": [],
            }
        messages = session_data.get("messages", [])
        # Add the new user message
        messages.append({"role": "user", "content": initial_message})
        # Keep only last 20 messages to avoid context window overflow
        if len(messages) > 20:
            messages = messages[-20:]
            session_data["messages"] = messages
    else:
        sid = session_store.new_session_id()
        messages = [{"role": "user", "content": initial_message}]
        session_data = {
            "session_id": sid,
            "messages": messages,
            "agent_calls": [],
        }

    # Load memory context so the orchestrator knows what the agents know
    mem_context = ""
    facts = memory.read_facts()
    learnings = memory.read_learnings()
    decisions = memory.read_decisions()
    tasks = memory.read_tasks()
    brand_constraints = memory.read_brand_constraints()
    if facts or learnings or decisions:
        def _recent(text: str, n: int = 15) -> str:
            lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
            return "\n".join(lines[:n])
        mem_context = f"\n\nMemory context (from blackboard):\nFacts:\n{_recent(facts)}\nLearnings:\n{_recent(learnings)}\nDecisions:\n{_recent(decisions)}"
        if tasks.strip():
            mem_context += f"\nActive tasks:\n{_recent(tasks, n=5)}"

    if brand_constraints:
        # Truncate to avoid context overflow
        mem_context += f"\n\nBrand Constraints (from Brand Agent):\n{brand_constraints[:2000]}"

    orchestrator_system = ORCHESTRATOR_SYSTEM_PROMPT + mem_context

    # Arm the cooperative-stop flag for this session
    with _stop_lock:
        _stop_flags[sid] = False

    try:
        # Step 1: Send session_id to frontend
        yield {"type": "session_id", "session_id": sid}

        # Step 1.5: plan preview — REMOVED (2026-09-01).
        # It cost a full extra LLM call on every user message just to render
        # 2-5 bullet points. Iteration 1 restores the "plan" event
        # deterministically from the selected flow's node list (zero calls).

        # Step 2: First LLM call — decide routing
        yield {"type": "status", "content": "Thinking..."}

        # Stream the orchestrator's own reply. This is the message the user
        # waits on with nothing on screen — asking for the market, or
        # presenting results. Measured 2026-09-01: the full completion takes
        # 15-70s depending on how much prose the model writes, but the first
        # token arrives at ~2s. Chunking a finished string (what this used to
        # do) threw that away and made every reply feel like a stall.
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        for event in llm.chat_stream(
            messages,
            system=orchestrator_system,
            tools=orchestrator_tools,
            temperature=0.3,
        ):
            if event["type"] == "delta":
                content_parts.append(event["content"])
                yield {"type": "text", "content": event["content"]}
            else:
                tool_calls = event.get("tool_calls") or []
            _check_stop(sid)

        content = "".join(content_parts)
        if content:
            messages.append({"role": "assistant", "content": content})

        # Step 2: Process tool calls (route to agents)
        agent_responses = []
        for tc in tool_calls:
            _check_stop(sid)
            tool_name = tc["name"]
            tool_args, parse_error = llm.safe_parse_tool_args(tc["arguments"])
            if parse_error is not None:
                print(f"[Orchestrator] Skipping {tool_name}: {parse_error}")
                yield {"type": "status", "content": f"Skipped {tool_name} (unreadable arguments)"}
                continue

            if tool_name == "seo_agent":
                task = tool_args.get("task", "")
                context = tool_args.get("context", "")
                flow_id = tool_args.get("flow") or ""
                if flow_id not in flows.REGISTRY:
                    flow_id = ""

                # Plan preview, straight from the flow's node list. This used
                # to cost a dedicated LLM call on every message.
                plan_steps = flows.plan_for(flow_id)
                if plan_steps:
                    yield {"type": "plan", "steps": plan_steps, "agent": "seo_agent",
                           "flow": flow_id}

                yield {
                    "type": "tool_start",
                    "tool": "seo_agent",
                    "args": {"task": task, "context": context[:100]}
                }
                yield {"type": "status", "content": f"Running SEO agent: {task}..."}

                agent_message = f"{task}\n\n{context}".strip()
                run_id = f"chat-{sid}"
                # User approved continuing after a budget stop → extend the cap
                if initial_message.strip().lower() in _CONTINUATION_WORDS:
                    from .tools.dataforseo import continue_dfs_budget

                    new_cap = continue_dfs_budget(run_id)
                    if new_cap:
                        yield {
                            "type": "status",
                            "content": f"DataForSEO budget extended to {new_cap} calls",
                        }
                pipeline_recorder.begin_run(run_id, initial_message or task)
                before_stages = pipeline_recorder.stage_ids(run_id)

                # Run the agent in a worker thread so this generator can
                # stream stage events live instead of blocking until done.
                # The copied context carries the active run id, so tool
                # recording and DFS budgeting still key to this run.
                ctx = contextvars.copy_context()
                worker_outcome: dict = {}

                def _worker():
                    try:
                        worker_outcome["result"] = ctx.run(
                            run_agent, agent_message,
                            stop_check=lambda: _check_stop(sid),
                            flow_id=flow_id or None,
                        )
                    except BaseException as exc:
                        worker_outcome["error"] = exc

                worker = threading.Thread(target=_worker, daemon=True)
                worker.start()

                seen_stages = set(before_stages)
                act_cursor = 0
                try:
                    while True:
                        worker.join(timeout=0.5)
                        activity, act_cursor = pipeline_recorder.new_activity(run_id, act_cursor)
                        for ev in activity:
                            yield {"type": "activity", "run_id": run_id, **ev}
                        for stage in pipeline_recorder.new_stages(run_id, seen_stages):
                            seen_stages.add(stage["stage_id"])
                            yield {"type": "stage", "run_id": run_id, **stage}
                        if not worker.is_alive():
                            break
                        # Stop must not wait for a hung network call: abandon
                        # the daemon worker and close the run right away.
                        with _stop_lock:
                            stopped_now = bool(_stop_flags.get(sid))
                        if stopped_now:
                            worker_outcome["error"] = StopRequested("stopped by user")
                            break
                except GeneratorExit:
                    # Client went away mid-run: ask the agent to stop and
                    # close the run so it doesn't stay "running" forever.
                    request_stop(sid)
                    worker.join(timeout=5)
                    if "result" in worker_outcome:
                        pipeline_recorder.end_run(run_id)
                    else:
                        pipeline_recorder.fail_run(
                            run_id, str(worker_outcome.get("error") or "stream closed")
                        )
                    raise

                # Drain anything the worker logged in its final half-second
                activity, act_cursor = pipeline_recorder.new_activity(run_id, act_cursor)
                for ev in activity:
                    yield {"type": "activity", "run_id": run_id, **ev}

                if "error" in worker_outcome:
                    err = worker_outcome["error"]
                    if isinstance(err, StopRequested):
                        pipeline_recorder.end_run(run_id, status="stopped")
                        session_data["agent_calls"].append({
                            "task": task,
                            "context": context,
                            "agent_session_id": None,
                            "tool_calls": 0,
                            "response": "Stopped by user",
                        })
                        yield {
                            "type": "tool_end",
                            "tool": "seo_agent",
                            "result": {"response": "Stopped by user", "tool_calls_made": 0},
                            "success": False,
                        }
                        yield {"type": "status", "content": "Stopped"}
                        break
                    print(f"[Orchestrator] seo_agent worker failed: {err!r}")
                    pipeline_recorder.fail_run(run_id, str(err))
                    session_data["agent_calls"].append({
                        "task": task,
                        "context": context,
                        "agent_session_id": None,
                        "tool_calls": 0,
                        "response": f"SEO agent failed: {err}",
                    })
                    yield {
                        "type": "tool_end",
                        "tool": "seo_agent",
                        "result": {"response": f"SEO agent failed: {err}", "tool_calls_made": 0},
                        "success": False,
                    }
                    yield {"type": "error", "content": str(err)}
                    continue

                pipeline_recorder.end_run(run_id)
                result = worker_outcome["result"]

                assistant_messages = [m for m in result["messages"] if m.get("role") == "assistant" and m.get("content")]
                agent_response = assistant_messages[-1]["content"] if assistant_messages else "No response"

                session_data["agent_calls"].append({
                    "task": task,
                    "context": context,
                    "agent_session_id": result["session_id"],
                    "tool_calls": len(result["tool_results"]),
                    "response": agent_response,
                })

                yield {
                    "type": "tool_end",
                    "tool": "seo_agent",
                    "result": {
                        "response": agent_response[:200] + "..." if len(agent_response) > 200 else agent_response,
                        "tool_calls_made": len(result["tool_results"])
                    },
                    "success": True
                }

                # Keep the agent's answer in the conversation. Without this the
                # orchestrator forgot every result the moment it streamed it, so
                # a follow-up like "drop that cluster, I prefer the other one"
                # had nothing to refer to and started a fresh run.
                if agent_response:
                    messages.append({"role": "assistant", "content": agent_response})

                # Yield the agent's response directly in chunks for streaming
                if agent_response:
                    yield {"type": "status", "content": "Writing response..."}
                    chunk_size = 30
                    for i in range(0, len(agent_response), chunk_size):
                        yield {"type": "text", "content": agent_response[i:i+chunk_size]}

            elif tool_name == "brand_agent":
                task = tool_args.get("task", "")
                context = tool_args.get("context", "")

                yield {
                    "type": "tool_start",
                    "tool": "brand_agent",
                    "args": {"task": task, "context": context[:100]}
                }
                yield {"type": "status", "content": f"Running Brand agent: {task}..."}

                agent_message = f"{task}\n\n{context}".strip()
                result = run_brand_agent(agent_message)

                assistant_messages = [m for m in result["messages"] if m.get("role") == "assistant" and m.get("content")]
                agent_response = assistant_messages[-1]["content"] if assistant_messages else "No response"

                session_data["agent_calls"].append({
                    "task": task,
                    "context": context,
                    "agent_session_id": result["session_id"],
                    "tool_calls": len(result["tool_results"]),
                    "response": agent_response,
                })

                yield {
                    "type": "tool_end",
                    "tool": "brand_agent",
                    "result": {
                        "response": agent_response[:200] + "..." if len(agent_response) > 200 else agent_response,
                        "tool_calls_made": len(result["tool_results"])
                    },
                    "success": True
                }

                if agent_response:
                    messages.append({"role": "assistant", "content": agent_response})
                if agent_response:
                    yield {"type": "status", "content": "Writing response..."}
                    chunk_size = 30
                    for i in range(0, len(agent_response), chunk_size):
                        yield {"type": "text", "content": agent_response[i:i+chunk_size]}

            elif tool_name == "builder_agent":
                task = tool_args.get("task", "")
                context = tool_args.get("context", "")

                yield {
                    "type": "tool_start",
                    "tool": "builder_agent",
                    "args": {"task": task, "context": context[:100]}
                }
                yield {"type": "status", "content": f"Running Builder agent: {task}..."}

                agent_message = f"{task}\n\n{context}".strip()
                result = run_builder_agent(agent_message)

                assistant_messages = [m for m in result["messages"] if m.get("role") == "assistant" and m.get("content")]
                agent_response = assistant_messages[-1]["content"] if assistant_messages else "No response"

                session_data["agent_calls"].append({
                    "task": task,
                    "context": context,
                    "agent_session_id": result["session_id"],
                    "tool_calls": len(result["tool_results"]),
                    "response": agent_response,
                })

                yield {
                    "type": "tool_end",
                    "tool": "builder_agent",
                    "result": {
                        "response": agent_response[:200] + "..." if len(agent_response) > 200 else agent_response,
                        "tool_calls_made": len(result["tool_results"])
                    },
                    "success": True
                }

                if agent_response:
                    messages.append({"role": "assistant", "content": agent_response})
                if agent_response:
                    yield {"type": "status", "content": "Writing response..."}
                    chunk_size = 30
                    for i in range(0, len(agent_response), chunk_size):
                        yield {"type": "text", "content": agent_response[i:i+chunk_size]}

            elif tool_name == "monitoring_agent":
                task = tool_args.get("task", "")
                context = tool_args.get("context", "")

                yield {
                    "type": "tool_start",
                    "tool": "monitoring_agent",
                    "args": {"task": task, "context": context[:100]}
                }
                yield {"type": "status", "content": f"Running Monitoring agent: {task}..."}

                agent_message = f"{task}\n\n{context}".strip()
                result = run_monitoring_agent(agent_message)

                assistant_messages = [m for m in result["messages"] if m.get("role") == "assistant" and m.get("content")]
                agent_response = assistant_messages[-1]["content"] if assistant_messages else "No response"

                session_data["agent_calls"].append({
                    "task": task,
                    "context": context,
                    "agent_session_id": result["session_id"],
                    "tool_calls": len(result["tool_results"]),
                    "response": agent_response,
                })

                yield {
                    "type": "tool_end",
                    "tool": "monitoring_agent",
                    "result": {
                        "response": agent_response[:200] + "..." if len(agent_response) > 200 else agent_response,
                        "tool_calls_made": len(result["tool_results"])
                    },
                    "success": True
                }

                if agent_response:
                    messages.append({"role": "assistant", "content": agent_response})
                if agent_response:
                    yield {"type": "status", "content": "Writing response..."}
                    chunk_size = 30
                    for i in range(0, len(agent_response), chunk_size):
                        yield {"type": "text", "content": agent_response[i:i+chunk_size]}

        # Record the orchestrator task in memory
        task_desc = initial_message[:80]
        memory.post_task(task_desc)
        memory.complete_task(task_desc)

        # Save session
        session_store.save_session(sid, session_data)
        yield {"type": "done"}

    except StopRequested:
        yield {"type": "status", "content": "Stopped"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "error", "content": str(e)}
    finally:
        with _stop_lock:
            _stop_flags.pop(sid, None)


def route_to_agent(
    agent_name: str,
    task: str,
    context: str = "",
) -> dict[str, Any]:
    """
    Route a task to a specific agent.
    
    Args:
        agent_name: Name of the agent to call
        task: What the agent should do
        context: Relevant context for the task
        
    Returns:
        Agent result
    """
    if agent_name not in AGENT_REGISTRY:
        return {"error": f"Unknown agent: {agent_name}"}
    
    agent = AGENT_REGISTRY[agent_name]
    handler = agent["handler"]
    
    message = f"{task}\n\n{context}".strip()
    result = handler(message)
    
    return {
        "agent": agent_name,
        "session_id": result["session_id"],
        "tool_calls": len(result["tool_results"]),
        "messages": result["messages"],
    }
