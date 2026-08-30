"""Monitoring tools — track SEO performance, diagnose issues, generate reports."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta

import httpx

from .gsc import gsc_performance, gsc_inspect_url, gsc_list_sitemaps
from .dataforseo import serp_organic, keywords_for_site
from ..config import settings
from .. import llm
from .. import memory


def monitor_performance(site_url: str, days: int = 28, compare_previous: bool = True) -> dict:
    """Monitor SEO performance over a period, with optional comparison to previous period.

    Analyzes clicks, impressions, CTR, position, and identifies opportunities
    and issues using bubble chart logic.

    Args:
        site_url: The site URL as registered in GSC.
        days: Number of days to analyze.
        compare_previous: Whether to compare with the previous period of equal length.

    Returns:
        Dict with metrics, changes, opportunity queries, and alert level.
    """
    # Fetch current period performance
    current_data = gsc_performance(site_url, days=days, dimensions=["query"])
    current_rows = current_data.get("rows", []) if current_data.get("status") == "success" else []

    # Calculate current period totals
    total_clicks = sum(r.get("clicks", 0) for r in current_rows)
    total_impressions = sum(r.get("impressions", 0) for r in current_rows)
    avg_ctr = round((total_clicks / max(total_impressions, 1)) * 100, 2)
    avg_position = round(
        sum(r.get("position", 0) * r.get("impressions", 0) for r in current_rows)
        / max(total_impressions, 1), 1
    )

    metrics = {
        "clicks": total_clicks,
        "impressions": total_impressions,
        "ctr": f"{avg_ctr}%",
        "position": avg_position,
    }

    changes: dict = {}
    top_gaining_queries: list[dict] = []
    top_declining_queries: list[dict] = []
    new_queries: list[dict] = []
    lost_queries: list[dict] = []
    opportunity_queries: list[dict] = []
    snippet_issue_queries: list[dict] = []

    if compare_previous:
        # Fetch previous period
        previous_data = gsc_performance(site_url, days=days * 2, dimensions=["query"])
        previous_rows = previous_data.get("rows", []) if previous_data.get("status") == "success" else []

        # Filter previous rows to only the previous period (not overlapping with current)
        # Since gsc_performance returns top 25 by query, we compare query-level data
        prev_by_query: dict[str, dict] = {}
        for r in previous_rows:
            q = r.get("query", "")
            if q:
                prev_by_query[q] = r

        curr_by_query: dict[str, dict] = {}
        for r in current_rows:
            q = r.get("query", "")
            if q:
                curr_by_query[q] = r

        # Previous period totals (approximation from available data)
        prev_clicks = sum(r.get("clicks", 0) for r in previous_rows)
        prev_impressions = sum(r.get("impressions", 0) for r in previous_rows)
        prev_ctr = round((prev_clicks / max(prev_impressions, 1)) * 100, 2)
        prev_position = round(
            sum(r.get("position", 0) * r.get("impressions", 0) for r in previous_rows)
            / max(prev_impressions, 1), 1
        )

        # Calculate changes
        clicks_delta = total_clicks - prev_clicks
        clicks_pct = round((clicks_delta / max(prev_clicks, 1)) * 100, 1)
        impressions_delta = total_impressions - prev_impressions
        impressions_pct = round((impressions_delta / max(prev_impressions, 1)) * 100, 1)
        ctr_delta = round(avg_ctr - prev_ctr, 2)
        position_delta = round(avg_position - prev_position, 1)

        changes = {
            "clicks_change": f"{clicks_pct:+.1f}%",
            "clicks_delta": clicks_delta,
            "impressions_change": f"{impressions_pct:+.1f}%",
            "impressions_delta": impressions_delta,
            "ctr_change": f"{ctr_delta:+.2f}pp",
            "position_change": f"{position_delta:+.1f}",
        }

        # Identify top gaining queries (biggest click increase)
        click_changes: list[dict] = []
        for query, curr in curr_by_query.items():
            prev = prev_by_query.get(query, {})
            curr_clicks = curr.get("clicks", 0)
            prev_clicks_val = prev.get("clicks", 0)
            delta = curr_clicks - prev_clicks_val
            if delta > 0:
                click_changes.append({
                    "query": query,
                    "current_clicks": curr_clicks,
                    "previous_clicks": prev_clicks_val,
                    "click_increase": delta,
                    "current_position": curr.get("position", 0),
                })
        click_changes.sort(key=lambda x: x["click_increase"], reverse=True)
        top_gaining_queries = click_changes[:10]

        # Identify top declining queries (biggest click decrease)
        declining: list[dict] = []
        for query, prev in prev_by_query.items():
            curr = curr_by_query.get(query, {})
            if not curr:
                continue
            curr_clicks = curr.get("clicks", 0)
            prev_clicks_val = prev.get("clicks", 0)
            delta = curr_clicks - prev_clicks_val
            if delta < 0:
                declining.append({
                    "query": query,
                    "current_clicks": curr_clicks,
                    "previous_clicks": prev_clicks_val,
                    "click_decrease": abs(delta),
                    "current_position": curr.get("position", 0),
                })
        declining.sort(key=lambda x: x["click_decrease"], reverse=True)
        top_declining_queries = declining[:10]

        # New queries (present now, absent before)
        for query, curr in curr_by_query.items():
            if query not in prev_by_query:
                new_queries.append({
                    "query": query,
                    "clicks": curr.get("clicks", 0),
                    "impressions": curr.get("impressions", 0),
                    "position": curr.get("position", 0),
                })
        new_queries.sort(key=lambda x: x["clicks"], reverse=True)
        new_queries = new_queries[:10]

        # Lost queries (present before, absent now)
        for query, prev in prev_by_query.items():
            if query not in curr_by_query:
                lost_queries.append({
                    "query": query,
                    "previous_clicks": prev.get("clicks", 0),
                    "previous_impressions": prev.get("impressions", 0),
                    "previous_position": prev.get("position", 0),
                })
        lost_queries.sort(key=lambda x: x["previous_clicks"], reverse=True)
        lost_queries = lost_queries[:10]

    # Bubble chart analysis: opportunity and snippet-issue queries
    for row in current_rows:
        pos = row.get("position", 99)
        ctr = row.get("ctr", 0)
        impressions = row.get("impressions", 0)
        query = row.get("query", "")

        # Opportunity: low rank (position > 10) but high impressions and decent CTR potential
        if pos > 10 and impressions > 50 and ctr > 0:
            opportunity_queries.append({
                "query": query,
                "position": pos,
                "clicks": row.get("clicks", 0),
                "impressions": impressions,
                "ctr": f"{ctr}%",
                "opportunity": "Improve ranking to capture more clicks from existing impressions",
            })

        # Snippet issue: high rank (position < 5) but low CTR suggests snippet/title issues
        if pos < 5 and impressions > 20 and ctr < 10:
            snippet_issue_queries.append({
                "query": query,
                "position": pos,
                "clicks": row.get("clicks", 0),
                "impressions": impressions,
                "ctr": f"{ctr}%",
                "issue": "High rank but low CTR — title or meta description may need improvement",
            })

    opportunity_queries.sort(key=lambda x: x["impressions"], reverse=True)
    opportunity_queries = opportunity_queries[:10]
    snippet_issue_queries.sort(key=lambda x: x["impressions"], reverse=True)
    snippet_issue_queries = snippet_issue_queries[:10]

    # Determine alert level
    alert_level = "green"
    clicks_pct_val = float(changes.get("clicks_change", "+0%").replace("%", "").replace("+", "")) if changes else 0
    if clicks_pct_val < -20 or len(lost_queries) > 5:
        alert_level = "red"
    elif clicks_pct_val < -5 or len(lost_queries) > 2 or len(snippet_issue_queries) > 3:
        alert_level = "yellow"

    return {
        "site_url": site_url,
        "period_days": days,
        "metrics": metrics,
        "changes": changes,
        "top_gaining_queries": top_gaining_queries,
        "top_declining_queries": top_declining_queries,
        "new_queries": new_queries,
        "lost_queries": lost_queries,
        "opportunity_queries": opportunity_queries,
        "snippet_issue_queries": snippet_issue_queries,
        "alert_level": alert_level,
    }


def check_indexing_health(site_url: str, sample_urls: list[str] | None = None) -> dict:
    """Check indexing health via GSC sitemaps and optional URL inspections.

    Args:
        site_url: The site URL as registered in GSC.
        sample_urls: Optional list of specific URLs to inspect.

    Returns:
        Dict with sitemap status, indexing health, and recommendations.
    """
    # Check sitemaps
    sitemaps_data = gsc_list_sitemaps(site_url)
    sitemaps = sitemaps_data.get("sitemaps", []) if sitemaps_data.get("status") == "success" else []

    total_submitted = 0
    total_indexed = 0
    sitemap_issues: list[str] = []

    for sitemap in sitemaps:
        errors = sitemap.get("errors", 0)
        warnings = sitemap.get("warnings", 0)
        if errors > 0:
            sitemap_issues.append(f"Sitemap {sitemap.get('path', 'unknown')}: {errors} error(s)")
        if warnings > 0:
            sitemap_issues.append(f"Sitemap {sitemap.get('path', 'unknown')}: {warnings} warning(s)")

        # Extract submitted/indexed counts from contents
        for content in sitemap.get("contents", []):
            total_submitted += content.get("submitted", 0)
            total_indexed += content.get("indexed", 0)

    # Inspect sample URLs
    sampled_urls: list[dict] = []
    if sample_urls:
        for url in sample_urls[:10]:  # Limit to 10 inspections
            inspection = gsc_inspect_url(site_url, url)
            indexed = False
            issues: list[str] = []

            if inspection.get("status") == "success":
                verdict = inspection.get("verdict", "UNKNOWN")
                coverage = inspection.get("coverage_state", "")
                indexing_state = inspection.get("indexing_state", "")
                robots_state = inspection.get("robots_txt_state", "")
                page_fetch = inspection.get("page_fetch_state", "")

                indexed = verdict == "PASS" and "indexed" in coverage.lower() if coverage else False

                if verdict != "PASS":
                    issues.append(f"Verdict: {verdict}")
                if "not indexed" in coverage.lower() or "excluded" in coverage.lower():
                    issues.append(f"Coverage: {coverage}")
                if robots_state and robots_state != "ALLOWED":
                    issues.append(f"Robots.txt: {robots_state}")
                if page_fetch and page_fetch != "SUCCESSFUL":
                    issues.append(f"Page fetch: {page_fetch}")
                if indexing_state and "not" in indexing_state.lower():
                    issues.append(f"Indexing: {indexing_state}")
            else:
                issues.append(f"Inspection failed: {inspection.get('status', 'unknown')}")

            sampled_urls.append({
                "url": url,
                "indexed": indexed,
                "issues": issues,
            })

    # Determine overall status
    coverage_pct = round((total_indexed / max(total_submitted, 1)) * 100, 1)
    if sitemap_issues or coverage_pct < 50:
        indexing_status = "errors"
    elif coverage_pct < 80 or any(u.get("issues") for u in sampled_urls):
        indexing_status = "warnings"
    else:
        indexing_status = "healthy"

    # Generate recommendations
    recommendations: list[str] = []
    if total_submitted == 0:
        recommendations.append("No sitemaps found — submit a sitemap to improve indexing visibility")
    if coverage_pct < 50 and total_submitted > 0:
        recommendations.append(
            f"Only {coverage_pct}% of submitted pages are indexed — check for noindex tags, "
            "thin content, or crawl budget issues"
        )
    if sitemap_issues:
        recommendations.append(f"Fix sitemap issues: {'; '.join(sitemap_issues[:3])}")
    not_indexed = [u for u in sampled_urls if not u.get("indexed")]
    if not_indexed:
        recommendations.append(
            f"{len(not_indexed)} of {len(sampled_urls)} sampled URLs are not indexed — "
            "inspect individual URLs for specific issues"
        )
    if not recommendations:
        recommendations.append("Indexing looks healthy — continue monitoring for changes")

    return {
        "site_url": site_url,
        "sitemaps": sitemaps,
        "indexing_status": indexing_status,
        "sampled_urls": sampled_urls,
        "total_submitted": total_submitted,
        "total_indexed": total_indexed,
        "coverage_pct": f"{coverage_pct}%",
        "recommendations": recommendations,
    }


def diagnose_traffic_drop(site_url: str, days_back: int = 30) -> dict:
    """Systematically diagnose the cause of a traffic drop.

    Gathers performance data, indexing status, and uses LLM analysis to
    determine the most likely cause.

    Args:
        site_url: The site URL as registered in GSC.
        days_back: Number of days to analyze for the drop.

    Returns:
        Dict with diagnosis, evidence, and recommended actions.
    """
    # Gather performance data
    current_perf = gsc_performance(site_url, days=days_back, dimensions=["date"])
    current_rows = current_perf.get("rows", []) if current_perf.get("status") == "success" else []

    previous_perf = gsc_performance(site_url, days=days_back * 2, dimensions=["date"])
    previous_rows = previous_perf.get("rows", []) if previous_perf.get("status") == "success" else []

    # Calculate totals
    current_clicks = sum(r.get("clicks", 0) for r in current_rows)
    previous_clicks = sum(r.get("clicks", 0) for r in previous_rows)
    current_impressions = sum(r.get("impressions", 0) for r in current_rows)
    previous_impressions = sum(r.get("impressions", 0) for r in previous_rows)

    clicks_change_pct = round(((current_clicks - previous_clicks) / max(previous_clicks, 1)) * 100, 1)
    impressions_change_pct = round(
        ((current_impressions - previous_impressions) / max(previous_impressions, 1)) * 100, 1
    )

    drop_confirmed = clicks_change_pct < -10

    # Check indexing status
    indexing_data = check_indexing_health(site_url)

    # Gather query-level data for analysis
    query_data = gsc_performance(site_url, days=days_back, dimensions=["query"])
    query_rows = query_data.get("rows", []) if query_data.get("status") == "success" else []

    # Known Google algorithm update dates (major ones)
    known_updates = {
        "2024-03-06": "March 2024 Core Update",
        "2024-06-27": "June 2024 Spam Update",
        "2024-08-15": "August 2024 Core Update",
        "2024-11-11": "November 2024 Core Update",
        "2025-02-05": "February 2025 Core Update",
        "2025-06-10": "June 2025 Core Update",
        "2025-09-15": "September 2025 Spam Update",
        "2025-12-01": "December 2025 Core Update",
        "2026-03-10": "March 2026 Core Update",
        "2026-06-20": "June 2026 Core Update",
    }

    # Check if drop aligns with a known update
    evidence: list[str] = []
    end_date = datetime.now() - timedelta(days=3)
    start_date = end_date - timedelta(days=days_back)

    for update_date_str, update_name in known_updates.items():
        update_date = datetime.strptime(update_date_str, "%Y-%m-%d")
        if start_date <= update_date <= end_date:
            evidence.append(f"Known Google update during period: {update_name} ({update_date_str})")

    # Add performance evidence
    evidence.append(
        f"Clicks changed {clicks_change_pct:+.1f}% ({previous_clicks} → {current_clicks})"
    )
    evidence.append(
        f"Impressions changed {impressions_change_pct:+.1f}% ({previous_impressions} → {current_impressions})"
    )

    # Indexing evidence
    if indexing_data.get("indexing_status") != "healthy":
        evidence.append(f"Indexing status: {indexing_data.get('indexing_status')}")
        for rec in indexing_data.get("recommendations", []):
            evidence.append(f"Indexing issue: {rec}")

    # Query-level evidence
    if query_rows:
        top_queries = sorted(query_rows, key=lambda r: r.get("clicks", 0), reverse=True)[:5]
        evidence.append(
            f"Top queries: {', '.join(r.get('query', '?') for r in top_queries)}"
        )

    # Use LLM to analyze and diagnose
    diagnostic_prompt = f"""You are an SEO traffic drop diagnostician. Analyze the following data and determine the most likely cause.

Site: {site_url}
Period: last {days_back} days
Clicks change: {clicks_change_pct:+.1f}% ({previous_clicks} → {current_clicks})
Impressions change: {impressions_change_pct:+.1f}% ({previous_impressions} → {current_impressions})
Indexing status: {indexing_data.get("indexing_status", "unknown")}
Evidence gathered:
{json.dumps(evidence, indent=2)}

Top queries this period:
{json.dumps(query_rows[:10], indent=2)}

Analyze whether this is:
1. algorithmic — caused by a Google core/spam update
2. technical — server errors, robots.txt, noindex tags, crawl issues
3. seasonal — normal industry fluctuation
4. competitive — competitors gaining ground
5. content_quality — content no longer satisfying search intent
6. unknown — insufficient data to diagnose

Respond with a JSON object:
{{
    "diagnosis": "algorithmic|technical|seasonal|competitive|content_quality|unknown",
    "confidence": "high|medium|low",
    "reasoning": "brief explanation of why",
    "recommended_actions": ["action1", "action2", ...]
}}
"""

    system_prompt = (
        "You are an expert SEO analyst specializing in diagnosing traffic drops. "
        "Always respond with valid JSON matching the requested schema. "
        "Be specific and actionable — avoid generic advice."
    )

    try:
        llm_resp = llm.chat(
            [{"role": "user", "content": diagnostic_prompt}],
            system=system_prompt,
            temperature=0.2,
        )
        parsed = llm.parse_json_response(llm_resp)
        diagnosis = parsed.get("diagnosis", "unknown") if isinstance(parsed, dict) else "unknown"
        confidence = parsed.get("confidence", "low") if isinstance(parsed, dict) else "low"
        recommended_actions = parsed.get("recommended_actions", []) if isinstance(parsed, dict) else []
        reasoning = parsed.get("reasoning", "") if isinstance(parsed, dict) else ""
        if reasoning:
            evidence.append(f"LLM analysis: {reasoning}")
    except Exception as e:
        diagnosis = "unknown"
        confidence = "low"
        recommended_actions = ["Manual review required — automated diagnosis failed"]
        evidence.append(f"LLM diagnosis failed: {e}")

    return {
        "site_url": site_url,
        "drop_confirmed": drop_confirmed,
        "drop_magnitude": f"{clicks_change_pct:+.1f}%",
        "diagnosis": diagnosis,
        "evidence": evidence,
        "recommended_actions": recommended_actions,
        "confidence": confidence,
    }


def monitor_keyword_rankings(
    domain: str,
    keywords: list[str],
    location_code: int = 2840,
    language_code: str = "en",
) -> dict:
    """Track keyword rankings for a domain in organic search results.

    Args:
        domain: The domain to track (e.g., "example.com").
        keywords: List of keywords to check.
        location_code: DataForSEO location code (default: 2840 = Bulgaria).
        language_code: Language code for SERP results.

    Returns:
        Dict with per-keyword rankings and summary statistics.
    """
    # Normalize domain for comparison
    domain_clean = domain.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if domain_clean.startswith(prefix):
            domain_clean = domain_clean[len(prefix):]
    domain_clean = domain_clean.rstrip("/")

    rankings: list[dict] = []
    positions: list[int] = []
    keywords_in_top_10 = 0
    keywords_not_found = 0

    for keyword in keywords:
        try:
            serp_results = serp_organic(
                keyword,
                location_code=location_code,
                language_code=language_code,
                depth=20,
            )
        except Exception as e:
            rankings.append({
                "keyword": keyword,
                "position": None,
                "in_top_3": False,
                "in_top_10": False,
                "competitors_above": [],
                "error": str(e),
            })
            keywords_not_found += 1
            continue

        # Find domain in results
        domain_position = None
        competitors_above: list[str] = []

        for result in serp_results:
            result_domain = result.get("domain", "").lower().rstrip("/")
            result_rank = result.get("rank", 99)

            if domain_clean in result_domain or result_domain in domain_clean:
                domain_position = result_rank
                break
            else:
                competitors_above.append(result_domain)

        in_top_3 = domain_position is not None and domain_position <= 3
        in_top_10 = domain_position is not None and domain_position <= 10

        if domain_position is not None:
            positions.append(domain_position)
            if in_top_10:
                keywords_in_top_10 += 1
        else:
            keywords_not_found += 1

        rankings.append({
            "keyword": keyword,
            "position": domain_position,
            "in_top_3": in_top_3,
            "in_top_10": in_top_10,
            "competitors_above": competitors_above[:5],
        })

    avg_position = round(sum(positions) / max(len(positions), 1), 1) if positions else None

    return {
        "domain": domain,
        "keywords_tracked": len(keywords),
        "rankings": rankings,
        "avg_position": avg_position,
        "keywords_in_top_10": keywords_in_top_10,
        "keywords_not_found": keywords_not_found,
    }


def content_freshness_alert(
    site_url: str,
    urls: list[str],
    stale_threshold_months: int = 6,
) -> dict:
    """Check content freshness for a list of URLs and alert on stale content.

    For each URL, attempts to extract date signals from the page and compares
    against the threshold.

    Args:
        site_url: Base site URL for context.
        urls: List of URLs to check.
        stale_threshold_months: Number of months after which content is considered stale.

    Returns:
        Dict with per-URL freshness data and summary.
    """
    threshold_date = datetime.now(timezone.utc) - timedelta(days=stale_threshold_months * 30)
    alerts: list[dict] = []
    fresh_count = 0
    stale_count = 0
    unknown_count = 0

    for url in urls:
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "SEO-Monitor/1.0"})
                html = resp.text[:50000]  # Limit to 50KB

            # Try to extract date signals from HTML
            last_updated = _extract_date_from_html(html)

            if last_updated is None:
                unknown_count += 1
                continue

            days_stale = (datetime.now(timezone.utc) - last_updated).days
            if last_updated < threshold_date:
                stale_count += 1
                severity = "critical" if days_stale > stale_threshold_months * 60 else "warning"
                alerts.append({
                    "url": url,
                    "last_updated": last_updated.strftime("%Y-%m-%d"),
                    "days_stale": days_stale,
                    "severity": severity,
                })
            else:
                fresh_count += 1

        except Exception as e:
            unknown_count += 1
            alerts.append({
                "url": url,
                "last_updated": None,
                "days_stale": None,
                "severity": "warning",
                "error": f"Could not fetch: {e}",
            })

    # Sort alerts by severity (critical first) then by staleness
    alerts.sort(key=lambda a: (0 if a.get("severity") == "critical" else 1, -(a.get("days_stale") or 0)))

    summary = (
        f"Checked {len(urls)} URLs: {fresh_count} fresh, {stale_count} stale, "
        f"{unknown_count} unknown. "
    )
    if stale_count > 0:
        summary += f"{stale_count} pages need updating — prioritize critical items."
    elif fresh_count == len(urls):
        summary += "All content is up to date."
    else:
        summary += f"{unknown_count} pages have no detectable date signals."

    return {
        "site_url": site_url,
        "urls_checked": len(urls),
        "alerts": alerts,
        "fresh_count": fresh_count,
        "stale_count": stale_count,
        "unknown_count": unknown_count,
        "summary": summary,
    }


def generate_monitoring_report(
    site_url: str,
    performance_data: dict | None = None,
    indexing_data: dict | None = None,
    rankings_data: dict | None = None,
    freshness_data: dict | None = None,
) -> dict:
    """Generate a comprehensive monitoring report combining data from multiple sources.

    Uses LLM to synthesize data into a human-readable report with health scoring,
    alerts, and prioritized action items.

    Args:
        site_url: The site URL.
        performance_data: Output from monitor_performance.
        indexing_data: Output from check_indexing_health.
        rankings_data: Output from monitor_keyword_rankings.
        freshness_data: Output from content_freshness_alert.

    Returns:
        Dict with overall health score, summary, alerts, and action items.
    """
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Calculate health score based on available data
    health_score = 100
    alerts: list[dict] = []

    if performance_data:
        alert_level = performance_data.get("alert_level", "green")
        if alert_level == "red":
            health_score -= 30
        elif alert_level == "yellow":
            health_score -= 15

        lost = performance_data.get("lost_queries", [])
        if lost:
            alerts.append({
                "type": "performance",
                "severity": "warning" if len(lost) < 5 else "critical",
                "message": f"{len(lost)} queries lost from search results",
            })

        snippet_issues = performance_data.get("snippet_issue_queries", [])
        if snippet_issues:
            alerts.append({
                "type": "snippet",
                "severity": "warning",
                "message": f"{len(snippet_issues)} queries with high rank but low CTR",
            })

    if indexing_data:
        status = indexing_data.get("indexing_status", "healthy")
        if status == "errors":
            health_score -= 25
            alerts.append({
                "type": "indexing",
                "severity": "critical",
                "message": f"Indexing errors detected — {', '.join(indexing_data.get('recommendations', [])[:2])}",
            })
        elif status == "warnings":
            health_score -= 10
            alerts.append({
                "type": "indexing",
                "severity": "warning",
                "message": "Indexing warnings detected — review recommendations",
            })

    if rankings_data:
        not_found = rankings_data.get("keywords_not_found", 0)
        tracked = rankings_data.get("keywords_tracked", 1)
        if not_found > tracked * 0.5:
            health_score -= 15
            alerts.append({
                "type": "rankings",
                "severity": "warning",
                "message": f"{not_found}/{tracked} tracked keywords not found in top results",
            })

    if freshness_data:
        stale = freshness_data.get("stale_count", 0)
        checked = freshness_data.get("urls_checked", 1)
        if stale > checked * 0.3:
            health_score -= 10
            alerts.append({
                "type": "freshness",
                "severity": "warning",
                "message": f"{stale}/{checked} pages have stale content",
            })

    health_score = max(0, min(100, health_score))

    if health_score >= 85:
        overall_health = "excellent"
    elif health_score >= 65:
        overall_health = "good"
    elif health_score >= 40:
        overall_health = "needs_attention"
    else:
        overall_health = "critical"

    # Use LLM to generate executive summary and priorities
    all_data = {
        "performance": performance_data,
        "indexing": indexing_data,
        "rankings": rankings_data,
        "freshness": freshness_data,
        "health_score": health_score,
        "alerts": alerts,
    }

    report_prompt = f"""You are an SEO reporting specialist. Generate a concise executive summary and prioritized action items.

Site: {site_url}
Report date: {report_date}
Overall health: {overall_health} (score: {health_score}/100)
Alerts: {json.dumps(alerts, indent=2)}

Data summary:
{json.dumps({k: v for k, v in all_data.items() if v is not None}, indent=2, default=str)[:3000]}

Respond with a JSON object:
{{
    "executive_summary": "2-3 sentence overview of site health and key findings",
    "priorities": [
        {{"priority": 1, "area": "area name", "action": "what to do", "expected_impact": "high|medium|low"}}
    ],
    "action_items": ["specific action 1", "specific action 2", ...]
}}
"""

    system_prompt = (
        "You are an expert SEO analyst writing executive reports. "
        "Be concise, specific, and actionable. Always respond with valid JSON."
    )

    try:
        llm_resp = llm.chat(
            [{"role": "user", "content": report_prompt}],
            system=system_prompt,
            temperature=0.2,
        )
        parsed = llm.parse_json_response(llm_resp)
        executive_summary = parsed.get("executive_summary", "") if isinstance(parsed, dict) else ""
        priorities = parsed.get("priorities", []) if isinstance(parsed, dict) else []
        action_items = parsed.get("action_items", []) if isinstance(parsed, dict) else []
    except Exception:
        executive_summary = f"Site health score: {health_score}/100 ({overall_health}). Review alerts for details."
        priorities = []
        action_items = [a.get("message", "") for a in alerts]

    # Build key metrics summary
    key_metrics: dict = {}
    if performance_data:
        key_metrics["clicks"] = performance_data.get("metrics", {}).get("clicks")
        key_metrics["impressions"] = performance_data.get("metrics", {}).get("impressions")
        key_metrics["ctr"] = performance_data.get("metrics", {}).get("ctr")
        key_metrics["avg_position"] = performance_data.get("metrics", {}).get("position")
    if indexing_data:
        key_metrics["indexing_status"] = indexing_data.get("indexing_status")
        key_metrics["coverage_pct"] = indexing_data.get("coverage_pct")
    if rankings_data:
        key_metrics["avg_keyword_position"] = rankings_data.get("avg_position")
        key_metrics["keywords_in_top_10"] = rankings_data.get("keywords_in_top_10")

    return {
        "site_url": site_url,
        "report_date": report_date,
        "overall_health": overall_health,
        "health_score": health_score,
        "executive_summary": executive_summary,
        "key_metrics": key_metrics,
        "alerts": alerts,
        "priorities": priorities,
        "action_items": action_items,
    }


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _extract_date_from_html(html: str) -> datetime | None:
    """Extract the most likely last-updated date from HTML content.

    Checks common meta tags, JSON-LD, and HTML patterns.
    """
    # Try JSON-LD dateModified
    json_ld_pattern = re.findall(r'"dateModified"\s*:\s*"([^"]+)"', html)
    for date_str in json_ld_pattern:
        parsed = _parse_date_string(date_str)
        if parsed:
            return parsed

    # Try meta tags
    meta_patterns = [
        r'<meta[^>]+property="article:modified_time"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="last-modified"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="revised"[^>]+content="([^"]+)"',
        r'<meta[^>]+property="og:updated_time"[^>]+content="([^"]+)"',
        r'<time[^>]+datetime="([^"]+)"',
    ]
    for pattern in meta_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for date_str in matches:
            parsed = _parse_date_string(date_str)
            if parsed:
                return parsed

    # Try datePublished as fallback
    pub_patterns = [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"',
    ]
    for pattern in pub_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for date_str in matches:
            parsed = _parse_date_string(date_str)
            if parsed:
                return parsed

    return None


def _parse_date_string(date_str: str) -> datetime | None:
    """Try to parse a date string into a datetime object."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%d %B %Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
