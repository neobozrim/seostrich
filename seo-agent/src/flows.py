"""Flow registry — the product's spine.

A flow is one named job the agent can do end to end: what it needs from the
user before it can start, which deterministic graph runs it, and which tools
the agent may touch while it runs.

This exists because "pick the right tool from 63" was never a decision the
model made reliably. Routing became: pick a FLOW, collect its required
inputs, hand off. Everything else keys off this registry — the homepage
cards, the plan preview, the WebMCP `seo_start_flow` tool, and the tool
allowlist for the agent turn — so they cannot drift apart.

Adding a flow means adding an entry here, not editing five call sites.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Input:
    """One thing the user must supply before a flow can run."""
    name: str
    label: str
    description: str
    required: bool = True
    # A market input is satisfied by confirm_market(), not by free text.
    kind: str = "text"  # text | market | url | list


@dataclass(frozen=True)
class Flow:
    id: str
    label: str
    tagline: str
    description: str
    inputs: list[Input]
    nodes: list[str]           # human-readable node list, shown as the plan
    tools: list[str]           # tools the agent may use inside this flow
    entrypoint: str            # the tool that runs the flow's graph
    stages: list[str]          # stage ids this flow is expected to produce
    icon: str = "workflow"


MARKET_INPUT = Input(
    name="market",
    label="Country & language",
    description=(
        "Which country your audience searches from, and in which language. "
        "Asked explicitly — never inferred from the domain or its TLD."
    ),
    kind="market",
)

BUSINESS_INPUT = Input(
    name="business_description",
    label="What the business does",
    description="Who it serves and what problem it solves, in the user's own words.",
)


KEYWORD_STRATEGY = Flow(
    id="keyword_strategy",
    label="Content strategy from scratch",
    tagline="Discovery → keywords → clusters → pillars",
    description=(
        "The full strategy graph: extract seeds in the market's own language, "
        "build a keyword universe from DataForSEO, over-cluster, gate on "
        "validation, score, select the few clusters that are actually relevant "
        "to the business, then brief content pillars off the selection."
    ),
    inputs=[
        BUSINESS_INPUT,
        MARKET_INPUT,
        Input("site_description", "Website", "The site's URL, if there is one.",
              required=False, kind="url"),
        Input("competitor_urls", "Competitors", "Known competitor URLs, up to 10. What they rank for goes into the keyword universe.",
              required=False, kind="list"),
    ],
    nodes=[
        "Confirm target market",
        "Read your own pages",
        "Extract keyword seeds",
        "Build keyword universe (DataForSEO) + what competitors rank for",
        "Cluster into themes",
        "Verify clusters against live SERPs",
        "Validation gate",
        "Measure, then select for the business",
        "Recommend content pillars",
        "Write the brief",
    ],
    tools=[
        "confirm_market", "list_markets", "run_keyword_strategy",
        "read_run_section",
        "list_clusters_all", "promote_cluster", "discard_cluster",
        "propose_cluster", "submit_deliverable", "plan_calendar",
    ],
    entrypoint="run_keyword_strategy",
    stages=["intake", "seeds", "keywords", "competitors", "clusters", "pillars", "brief"],
    icon="target",
)


GEO_DEMAND = Flow(
    id="geo_demand",
    label="AI visibility (GEO)",
    tagline="What AI engines answer, and who they cite",
    description=(
        "Research how AI engines already answer questions in this space: AI "
        "search demand per term, which sources get cited today, the open share "
        "left to win, and the real questions people ask (People-also-ask) — "
        "then brief answer-first content against them."
    ),
    inputs=[
        Input("head_terms", "Topics", "The head terms to investigate.", kind="list"),
        MARKET_INPUT,
    ],
    nodes=[
        "Confirm target market",
        "Measure real search demand per topic",
        "Check AI citability: who answers, who is cited, what is unclaimed",
        "Rank topics on measured evidence",
        "Harvest the actual questions people ask (top topics only)",
        "Answer-first content brief",
        "Optional: check which AI answers already cite your site",
    ],
    tools=[
        "confirm_market", "list_markets", "run_geo_demand",
        "read_run_section", "ai_citation_check", "ai_citability_brief", "ai_mentions",
        "serp_ai_mode", "submit_deliverable",
    ],
    entrypoint="run_geo_demand",
    stages=["intake", "ai_citability"],
    icon="sparkles",
)


REGISTRY: dict[str, Flow] = {f.id: f for f in (KEYWORD_STRATEGY, GEO_DEMAND)}

# Flows planned but not yet built as graphs. Listed so the UI and WebMCP can
# say "not yet" honestly instead of the agent improvising a half-flow.
PLANNED = {
    "reverse_strategy": "Reverse-engineer a strategy from an existing site or blog",
    "technical_audit": "Full technical SEO audit",
}


def get(flow_id: str) -> Flow | None:
    return REGISTRY.get(flow_id)


def list_flows() -> list[dict]:
    """Flow cards, for the homepage / WebMCP / the orchestrator's routing."""
    return [
        {
            "id": f.id,
            "label": f.label,
            "tagline": f.tagline,
            "description": f.description,
            "icon": f.icon,
            "nodes": f.nodes,
            "required_inputs": [
                {"name": i.name, "label": i.label, "description": i.description,
                 "kind": i.kind}
                for i in f.inputs if i.required
            ],
            "optional_inputs": [
                {"name": i.name, "label": i.label, "description": i.description,
                 "kind": i.kind}
                for i in f.inputs if not i.required
            ],
        }
        for f in REGISTRY.values()
    ]


def plan_for(flow_id: str) -> list[str]:
    """The plan preview — the flow's node list. Deterministic, costs no LLM call.

    This replaces the per-message planning LLM call the orchestrator used to
    make just to render a few bullets.
    """
    flow = get(flow_id)
    return list(flow.nodes) if flow else []


def missing_inputs(flow_id: str, provided: dict) -> list[Input]:
    """Required inputs the user has not supplied yet."""
    flow = get(flow_id)
    if not flow:
        return []
    missing = []
    for inp in flow.inputs:
        if not inp.required:
            continue
        value = provided.get(inp.name)
        if value is None or (isinstance(value, (str, list, dict)) and not value):
            missing.append(inp)
    return missing


def tools_for(flow_id: str) -> list[str]:
    """Tool allowlist for a flow, or [] when the flow is unknown."""
    flow = get(flow_id)
    return list(flow.tools) if flow else []
