from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}

_REDIRECT_TYPE_LABELS = {
    301: "301 Permanent",
    302: "302 Found (temporary)",
    303: "303 See Other (temporary)",
    307: "307 Temporary Redirect",
    308: "308 Permanent Redirect",
}


def check_redirects(urls: list[str], max_hops: int = 10) -> dict:
    """Follow redirects for each URL and report chains, loops, and issues."""
    if not urls:
        return {
            "results": [],
            "summary": {
                "total_checked": 0,
                "chains_found": 0,
                "loops_found": 0,
                "issues_found": 0,
            },
        }

    normalized: list[str] = []
    for u in urls:
        if not u.startswith("http"):
            u = f"https://{u}"
        normalized.append(u)

    results: list[dict] = []
    total_chains = 0
    total_loops = 0
    total_issues = 0

    with httpx.Client(
        timeout=15,
        follow_redirects=False,
        headers={"User-Agent": "SEOAgent/1.0"},
    ) as client:
        for url in normalized:
            chain: list[dict] = []
            current = url
            visited: list[str] = []
            final_url = url
            final_status = 0
            redirect_type = "none"
            issues: list[str] = []
            is_loop = False

            for hop in range(max_hops):
                if current in visited:
                    issues.append(f"Redirect loop detected at {current}")
                    is_loop = True
                    break
                visited.append(current)

                try:
                    resp = client.request("GET", current)
                except Exception as exc:
                    issues.append(f"Request failed at hop {hop + 1}: {exc}")
                    break

                status = resp.status_code
                hop_entry: dict = {
                    "url": current,
                    "status_code": status,
                    "redirect_type": _REDIRECT_TYPE_LABELS.get(status, str(status)),
                }
                chain.append(hop_entry)

                if status in _REDIRECT_STATUS_CODES:
                    location = resp.headers.get("location", "")
                    if not location:
                        issues.append(f"Redirect ({status}) with no Location header at {current}")
                        break

                    # Resolve relative Location
                    if location.startswith("/"):
                        from urllib.parse import urlparse

                        parsed = urlparse(current)
                        location = f"{parsed.scheme}://{parsed.netloc}{location}"
                    elif not location.startswith("http"):
                        location = current.rstrip("/") + "/" + location

                    # Set redirect type from first redirect
                    if hop == 0:
                        redirect_type = _REDIRECT_TYPE_LABELS.get(status, str(status))

                    current = location
                else:
                    final_url = current
                    final_status = status
                    break

            # If loop was detected, still set final info
            if is_loop:
                final_url = current
                final_status = 0

            # Chain length check
            hop_count = len(chain)
            if hop_count > 3:
                issues.append(f"Redirect chain has {hop_count} hops (> 3 is inefficient)")
                total_chains += 1

            # Soft 404: redirect to homepage
            if final_url and final_status == 200:
                from urllib.parse import urlparse

                original_parsed = urlparse(url)
                final_parsed = urlparse(final_url)
                if (
                    final_parsed.path in ("", "/")
                    and original_parsed.path not in ("", "/")
                ):
                    issues.append(
                        "Possible soft 404: URL redirects to homepage instead of 404"
                    )

            # Meta refresh / JS redirect on final page
            if final_status == 200:
                try:
                    resp_final = client.request("GET", final_url)
                    if resp_final.status_code == 200:
                        soup = BeautifulSoup(resp_final.text[:50_000], "html.parser")
                        # Meta refresh
                        meta_refresh = soup.find(
                            "meta", attrs={"http-equiv": re.compile(r"refresh", re.I)}
                        )
                        if meta_refresh:
                            issues.append(
                                f"Meta refresh detected on final page: "
                                f"{meta_refresh.get('content', '')}"
                            )
                        # JS redirect
                        js_redirect = re.search(
                            r"window\.location\s*[.=]", resp_final.text[:50_000]
                        )
                        if js_redirect:
                            issues.append("JavaScript redirect (window.location) detected on final page")
                except Exception:
                    pass

            total_issues += len(issues)
            if is_loop:
                total_loops += 1

            results.append({
                "url": url,
                "chain": chain,
                "final_url": final_url,
                "final_status": final_status,
                "redirect_type": redirect_type,
                "hop_count": hop_count,
                "issues": issues,
            })

    return {
        "results": results,
        "summary": {
            "total_checked": len(normalized),
            "chains_found": total_chains,
            "loops_found": total_loops,
            "issues_found": total_issues,
        },
    }
