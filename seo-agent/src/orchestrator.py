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


ORCHESTRATOR_SYSTEM_PROMPT = """You are an intelligent orchestrator agent. Your job is to:

1. Understand what the user wants to accomplish
2. Identify which specialist agent(s) can help
3. Route the task to the right agent with proper context
4. Present results back to the user
5. Continue the conversation as needed

**Available Agents:**

**SEO Agent** - Handles all SEO-related work:
- Keyword research and clustering
- Content strategy and planning
- Technical SEO audits
- Indexing and submission to search engines
- Search performance analysis (Google Search Console)
- Content creation and optimization

**Brand Agent** - Handles brand identity work:
- Founder interview and brand discovery
- Competitor convention mapping
- Voice, typography, and color system design
- Brand profile creation (brand_profile.json + brand-constraints.md)
- Naming and trademark verification
- Use when: creating brand identity for a new project, rebranding, defining voice/tone/visual identity

**Builder Agent** - Handles implementation with 3-tier verification:
- Autonomous code generation and building
- Asset generation (wordmarks, icons, illustrations, photos via fal.ai)
- 3-tier verification: mechanical → compliance (hard gate) → judgment
- Never changes brand profile — adjusts implementation instead
- Use when: building websites/apps, generating visual assets, implementing designs

**Monitoring Agent** - Tracks SEO performance and diagnoses issues:
- Performance monitoring with bubble chart analysis
- Indexing health checks and coverage tracking
- Traffic drop diagnosis (algorithmic vs technical vs seasonal)
- Keyword ranking tracking across SERPs
- Content freshness alerts
- Comprehensive monitoring reports with health scores
- Use when: checking site performance, diagnosing traffic drops, tracking rankings, monitoring indexing health

**Your Role:**
- Have a natural conversation to understand the user's goals
- Ask clarifying questions if needed
- When you identify work for a specialist, call the appropriate agent tool with:
  - Clear task description
  - Relevant context (business info, goals, constraints)
- Present the agent's results in a user-friendly way
- Ask what else they need

**Examples:**

User: "I have a new blog and want to grow traffic"
→ Ask about their business, target audience, goals
→ Once you have context, call seo_agent with task="Create SEO strategy" and context=business details

User: "I need branding for my new project"
→ Call brand_agent with task="Create brand identity" and context=project details

User: "Audit my site"
→ Ask for the URL
→ Call seo_agent with task="Technical SEO audit" and context=URL

**Important:**
- Don't try to do specialist work yourself
- Don't call agents unnecessarily (e.g., don't call for simple greetings)
- Maintain conversation flow
- Remember context across the conversation
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
                "description": "Route a task to the SEO specialist agent.",
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

        # Step 1.5: Generate plan (show to user, no confirmation needed)
        # This is the "planning" pattern from Andrew Ng's framework
        plan_prompt = f"""Based on the user's request, create a brief execution plan.
        
User request: {initial_message}

Output a JSON object with:
- "plan": array of 2-5 steps, each a short string describing what will be done
- "agent": which specialist agent will handle this (seo_agent, brand_agent, builder_agent, monitoring_agent)

If the request is simple or conversational (not requiring specialist work), return:
{{"plan": [], "agent": null}}

Be concise. Each step should be <10 words.
"""
        try:
            plan_resp = llm.chat(
                [{"role": "user", "content": plan_prompt}],
                system="You are a planning assistant. Output only valid JSON.",
                temperature=0.2,
            )
            plan_content = plan_resp.get("content", "")
            if plan_content:
                import json as json_lib
                plan_data = json_lib.loads(plan_content)
                plan_steps = plan_data.get("plan", [])
                if plan_steps:
                    # Stream plan to user (no confirmation — just transparency)
                    yield {"type": "plan", "steps": plan_steps, "agent": plan_data.get("agent")}
        except Exception:
            # Plan generation failed — continue without it
            pass

        # Step 2: First LLM call — decide routing
        yield {"type": "status", "content": "Thinking..."}

        resp = llm.chat(
            messages,
            system=orchestrator_system,
            tools=orchestrator_tools,
            temperature=0.3,
        )

        content = resp.get("content", "")
        tool_calls = resp.get("tool_calls", [])

        # Yield any direct text from orchestrator in chunks
        if content:
            messages.append({"role": "assistant", "content": content})
            chunk_size = 30
            for i in range(0, len(content), chunk_size):
                yield {"type": "text", "content": content[i:i+chunk_size]}

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
                        )
                    except BaseException as exc:
                        worker_outcome["error"] = exc

                worker = threading.Thread(target=_worker, daemon=True)
                worker.start()

                seen_stages = set(before_stages)
                try:
                    while True:
                        worker.join(timeout=0.5)
                        for stage in pipeline_recorder.new_stages(run_id, seen_stages):
                            seen_stages.add(stage["stage_id"])
                            yield {"type": "stage", "run_id": run_id, **stage}
                        if not worker.is_alive():
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
