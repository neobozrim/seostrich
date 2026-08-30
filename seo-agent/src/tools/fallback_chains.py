"""Tool fallback chains — automatic retry with alternative tools when primary tools fail."""
from __future__ import annotations

import traceback
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Fallback chain configuration
# ---------------------------------------------------------------------------

# Define fallback chains: primary_tool -> [fallback_tool_1, fallback_tool_2, ...]
#
# IMPORTANT: No DataForSEO fallbacks. web_search is NOT equivalent to DataForSEO
# keyword/SERP data — falling back to web search for keyword research produces
# hallucinated volumes and fabricated SERP analysis. If DataForSEO fails, tell
# the user and retry. Only non-data tools have fallbacks here.
FALLBACK_CHAINS: dict[str, list[str]] = {
    # GSC → Bing: both are real data sources (performance metrics, not guesses)
    "gsc_performance": ["get_site_keywords"],
    # Monolithic audit → composable sub-audits: same tool family, graceful degradation
    "technical_seo_audit": ["audit_crawlability", "audit_meta_tags"],
}

# Map tool names to descriptions of what they do (for fallback context)
TOOL_PURPOSES: dict[str, str] = {
    "web_search": "search the web for information",
    "gsc_performance": "get Google Search Console performance data",
    "get_site_keywords": "get top keywords from Bing Webmaster Tools",
    "technical_seo_audit": "run comprehensive technical SEO audit",
    "audit_crawlability": "audit site crawlability",
    "audit_meta_tags": "audit meta tags",
}


# ---------------------------------------------------------------------------
# Argument adaptation
# ---------------------------------------------------------------------------

def adapt_args_for_fallback(
    original_tool: str,
    fallback_tool: str,
    original_args: dict[str, Any],
) -> dict[str, Any]:
    """Adapt tool arguments when falling back to a different tool.

    Maps arguments from the original tool's expected format to the
    fallback tool's format so the fallback can be called with sensible
    parameters even when the two tools have different interfaces.

    Args:
        original_tool: Name of the tool that originally failed.
        fallback_tool: Name of the fallback tool being attempted.
        original_args: The arguments that were passed to the original tool.

    Returns:
        A new dict of arguments suitable for the fallback tool.
    """

    # -- gsc_performance → get_site_keywords ---------------------------------
    # Both return real performance data — GSC from Google, Bing from Bing.
    if original_tool == "gsc_performance" and fallback_tool == "get_site_keywords":
        return {
            "site_url": original_args.get("site_url", ""),
            "count": 50,
        }

    # -- technical_seo_audit → audit_crawlability / audit_meta_tags ----------
    # Same tool family — both accept a single ``url`` parameter.
    if original_tool == "technical_seo_audit" and fallback_tool in (
        "audit_crawlability",
        "audit_meta_tags",
    ):
        return {"url": original_args.get("url", "")}

    # -- Generic fallback: pass args through unchanged -----------------------
    return dict(original_args)


# ---------------------------------------------------------------------------
# Core execution with fallback
# ---------------------------------------------------------------------------

def execute_with_fallback(
    tool_name: str,
    tool_args: dict[str, Any],
    tool_callables: dict[str, Callable],
    original_error: str = "",
) -> dict[str, Any]:
    """Execute a tool with automatic fallback to alternatives.

    When a primary tool call has already failed (signalled by
    *original_error*), this function walks the configured fallback chain
    and tries each alternative tool in order, adapting arguments as
    needed.

    Args:
        tool_name: Name of the primary tool that failed.
        tool_args: Arguments that were originally passed to the primary tool.
        tool_callables: Map of tool names to callable functions.  Every
            tool in the fallback chain that should be attempted must have
            an entry here.
        original_error: Error message from the primary tool failure.  If
            empty, the primary tool is assumed to have succeeded and no
            fallback is attempted.

    Returns:
        A dict with the following keys:

        - **result** — The return value from whichever tool succeeded
          (``None`` if all failed).
        - **tool_used** — Name of the tool that actually produced the
          result (empty string if all failed).
        - **fallback_used** — ``True`` if a fallback tool was needed.
        - **fallback_chain** — List of tool names that were attempted
          (including the primary).
        - **errors** — List of ``(tool_name, error_message)`` tuples for
          every tool that failed.
    """

    errors: list[tuple[str, str]] = []
    chain_tried: list[str] = [tool_name]

    if original_error:
        errors.append((tool_name, original_error))

    # If no fallback chain is configured, return immediately.
    fallback_tools = FALLBACK_CHAINS.get(tool_name, [])
    if not fallback_tools:
        return {
            "result": None,
            "tool_used": "",
            "fallback_used": False,
            "fallback_chain": chain_tried,
            "errors": errors,
        }

    # Try each fallback tool in order.
    for fb_tool in fallback_tools:
        callable_fn = tool_callables.get(fb_tool)
        if callable_fn is None:
            chain_tried.append(fb_tool)
            errors.append((fb_tool, f"fallback tool '{fb_tool}' not registered in tool_callables"))
            continue

        adapted_args = adapt_args_for_fallback(tool_name, fb_tool, tool_args)
        chain_tried.append(fb_tool)

        try:
            result = callable_fn(**adapted_args)
            return {
                "result": result,
                "tool_used": fb_tool,
                "fallback_used": True,
                "fallback_chain": chain_tried,
                "errors": errors,
            }
        except Exception as exc:
            errors.append((fb_tool, f"{type(exc).__name__}: {exc}"))

    # All fallbacks exhausted.
    return {
        "result": None,
        "tool_used": "",
        "fallback_used": True,
        "fallback_chain": chain_tried,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def get_fallback_info(tool_name: str) -> dict[str, Any]:
    """Get fallback information for a tool.

    Useful for informing the LLM (or the developer) about what
    alternative tools are available when a given tool fails.

    Args:
        tool_name: Name of the tool to look up.

    Returns:
        A dict with:

        - **has_fallback** — ``True`` if at least one fallback is configured.
        - **fallback_tools** — List of fallback tool names (may be empty).
        - **purpose** — Human-readable description of what the tool does.
    """
    fallback_tools = FALLBACK_CHAINS.get(tool_name, [])
    return {
        "has_fallback": len(fallback_tools) > 0,
        "fallback_tools": list(fallback_tools),
        "purpose": TOOL_PURPOSES.get(tool_name, ""),
    }


def get_all_fallback_chains() -> dict[str, dict[str, Any]]:
    """Return fallback info for every configured tool, keyed by tool name.

    Handy for startup diagnostics or ``/tools status`` displays.
    """
    return {name: get_fallback_info(name) for name in FALLBACK_CHAINS}
