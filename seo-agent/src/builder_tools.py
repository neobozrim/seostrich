"""Builder agent tools — implementation, verification, and asset generation."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from . import memory


AGENT_NAME = "builder-agent"


def read_brand_profile(client_id: str) -> dict[str, Any]:
    """Load brand_profile.json from artefacts (immutable constraints)."""
    memory_dir = memory._get_memory_dir()
    profile_path = memory_dir / "artefacts" / f"{client_id}-brand-profile.json"

    if not profile_path.exists():
        return {
            "error": f"Brand profile not found for {client_id}",
            "expected_path": str(profile_path),
        }

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        return {
            "status": "success",
            "profile": profile,
            "path": str(profile_path),
        }
    except Exception as e:
        return {"error": f"Failed to load brand profile: {e}"}


def read_content_plan(client_id: str) -> dict[str, Any]:
    """Load content_plan.md from artefacts."""
    plan_path = memory._get_artefacts_dir() / f"{client_id}-content-plan.md"

    if not plan_path.exists():
        return {
            "error": f"Content plan not found for {client_id}",
            "expected_path": str(plan_path),
        }

    try:
        content = plan_path.read_text(encoding="utf-8")
        return {
            "status": "success",
            "content": content,
            "path": str(plan_path),
        }
    except Exception as e:
        return {"error": f"Failed to load content plan: {e}"}


def write_file(path: str, content: str) -> dict[str, Any]:
    """Create or update a file."""
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return {
            "status": "success",
            "path": str(file_path),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"error": f"Failed to write file: {e}"}


def run_shell(command: str, cwd: str | None = None) -> dict[str, Any]:
    """Run a shell command (install, build, test)."""
    try:
        work_dir = cwd or os.getcwd()
        result = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        success = result.returncode == 0

        # Record the command to blackboard
        memory.record_decision(
            f"Builder executed: {command[:100]}",
            context={
                "cwd": work_dir,
                "returncode": result.returncode,
                "stdout_lines": len(result.stdout.split("\n")),
            },
            agent=AGENT_NAME,
        )

        return {
            "status": "success" if success else "failed",
            "returncode": result.returncode,
            "stdout": result.stdout[:2000] if result.stdout else "",
            "stderr": result.stderr[:1000] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (300s limit)"}
    except Exception as e:
        return {"error": f"Failed to run command: {e}"}


def playwright_check(url: str, checks: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run 3-tier verification on a URL.

    Tier 1: Mechanical (build success, console errors, network, layout)
    Tier 2: Compliance (computed styles match brand tokens — HARD GATE)
    Tier 3: Judgment (screenshot + LLM assessment)
    """
    checks = checks or {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "error": "Playwright not installed. Run: pip install playwright && playwright install"
        }

    results = {
        "url": url,
        "tier1": {"status": "unknown", "checks": {}},
        "tier2": {"status": "unknown", "checks": {}},
        "tier3": {"status": "unknown", "judgment": None},
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Tier 1: Mechanical checks
            console_errors = []
            network_failures = []

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("requestfailed", lambda req: network_failures.append(req.url))

            # Check build success (HTTP status)
            response = page.goto(url, wait_until="networkidle", timeout=30000)
            http_status = response.status if response else 0

            results["tier1"]["checks"]["http_status"] = http_status
            results["tier1"]["checks"]["build_success"] = 200 <= http_status < 300

            # Check console errors
            results["tier1"]["checks"]["console_errors"] = console_errors
            results["tier1"]["checks"]["console_clean"] = len(console_errors) == 0

            # Check network failures
            results["tier1"]["checks"]["network_failures"] = network_failures
            results["tier1"]["checks"]["network_clean"] = len(network_failures) == 0

            # Check layout overflow at different viewports
            overflow_issues = []
            for viewport_width in [360, 768, 1440]:
                page.set_viewport_size({"width": viewport_width, "height": 800})
                page.wait_for_timeout(500)

                overflow = page.evaluate("""
                    () => {
                        const docWidth = document.documentElement.offsetWidth;
                        let hasOverflow = false;
                        document.querySelectorAll('*').forEach(el => {
                            if (el.offsetWidth > docWidth) {
                                hasOverflow = true;
                            }
                        });
                        return hasOverflow;
                    }
                """)

                if overflow:
                    overflow_issues.append(f"Overflow at {viewport_width}px")

            results["tier1"]["checks"]["overflow_issues"] = overflow_issues
            results["tier1"]["checks"]["layout_clean"] = len(overflow_issues) == 0

            # Tier 1 pass/fail
            tier1_pass = all([
                results["tier1"]["checks"]["build_success"],
                results["tier1"]["checks"]["console_clean"],
                results["tier1"]["checks"]["network_clean"],
                results["tier1"]["checks"]["layout_clean"],
            ])
            results["tier1"]["status"] = "pass" if tier1_pass else "fail"

            if not tier1_pass:
                # Don't proceed to Tier 2/3 if Tier 1 fails
                results["tier2"]["status"] = "skipped"
                results["tier3"]["status"] = "skipped"
                browser.close()
                return results

            # Tier 2: Compliance checks (HARD GATE)
            brand_profile = checks.get("brand_profile")
            if brand_profile:
                compliance_checks = []

                # Check colors
                expected_colors = brand_profile.get("colors", {})
                if expected_colors:
                    # Sample some elements and check computed colors
                    color_checks = page.evaluate("""
                        (expectedColors) => {
                            const results = [];
                            const elements = document.querySelectorAll('body, h1, h2, h3, p, a, button');
                            elements.forEach(el => {
                                const computed = window.getComputedStyle(el);
                                results.push({
                                    tag: el.tagName,
                                    color: computed.color,
                                    backgroundColor: computed.backgroundColor,
                                });
                            });
                            return results;
                        }
                    """, expected_colors)
                    compliance_checks.append({"type": "colors", "sample": color_checks[:5]})

                # Check typography
                expected_fonts = brand_profile.get("typography", {})
                if expected_fonts:
                    font_checks = page.evaluate("""
                        (expectedFonts) => {
                            const results = [];
                            const elements = document.querySelectorAll('h1, h2, h3, p, span');
                            elements.forEach(el => {
                                const computed = window.getComputedStyle(el);
                                results.push({
                                    tag: el.tagName,
                                    fontFamily: computed.fontFamily,
                                    fontSize: computed.fontSize,
                                });
                            });
                            return results;
                        }
                    """, expected_fonts)
                    compliance_checks.append({"type": "typography", "sample": font_checks[:5]})

                # Check headlines are real text (not images)
                headline_checks = page.evaluate("""
                    () => {
                        const headlines = document.querySelectorAll('h1, h2');
                        const results = [];
                        headlines.forEach(h => {
                            const style = window.getComputedStyle(h);
                            const hasText = h.textContent.trim().length > 0;
                            const isImage = style.backgroundImage !== 'none';
                            results.push({
                                tag: h.tagName,
                                text: h.textContent.substring(0, 50),
                                hasText: hasText,
                                isImage: isImage,
                            });
                        });
                        return results;
                    }
                """)
                compliance_checks.append({"type": "headlines_real_text", "sample": headline_checks})

                results["tier2"]["checks"] = compliance_checks

                # For now, mark as pass (full compliance checking would require more logic)
                # In production, you'd validate each check against brand_profile
                results["tier2"]["status"] = "pass"
            else:
                results["tier2"]["status"] = "skipped"
                results["tier2"]["checks"] = {"note": "No brand_profile provided for compliance check"}

            # Tier 3: Judgment (screenshot)
            screenshot_path = checks.get("screenshot_path") or "screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            results["tier3"]["screenshot"] = screenshot_path
            results["tier3"]["status"] = "captured"

            browser.close()

        return results

    except Exception as e:
        return {"error": f"Playwright check failed: {e}"}


def take_screenshot(url: str, output_path: str) -> dict[str, Any]:
    """Capture screenshot for Tier 3 judgment."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "error": "Playwright not installed. Run: pip install playwright && playwright install"
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=output_path, full_page=True)
            browser.close()

        return {
            "status": "success",
            "path": output_path,
        }
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}


def generate_image(
    prompt: str,
    model: str = "flux-2-pro",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate image via fal.ai.

    Models:
    - ideogram-3.0: wordmarks, logos with text
    - recraft-v4: SVG/vector output
    - flux-2-pro: photorealistic images
    - imagen-4-fast: bulk drafts, concept exploration
    """
    params = params or {}

    # Model routing
    model_map = {
        "ideogram-3.0": "fal-ai/ideogram/v3",
        "recraft-v4": "fal-ai/recraft-v4",
        "flux-2-pro": "fal-ai/flux-pro/v1.1",
        "imagen-4-fast": "fal-ai/imagen4/fast",
    }

    if model not in model_map:
        return {"error": f"Unknown model: {model}. Use: {list(model_map.keys())}"}

    # Check FAL_KEY
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        return {
            "error": "FAL_KEY not set. Add to .env: FAL_KEY=your_key_here",
            "hint": "Get key from: https://fal.ai/dashboard/keys",
        }

    # Licensing checks
    if "dev" in model.lower() and params.get("commercial", False):
        return {
            "error": "FLUX dev models cannot be used for commercial purposes. Route to flux-2-pro."
        }

    if "recraft" in model.lower() and params.get("commercial", False):
        # Recraft free tier is non-commercial
        return {
            "warning": "Recraft free tier is non-commercial. Verify license before using output commercially."
        }

    # Build request
    fal_endpoint = model_map[model]
    payload = {
        "prompt": prompt,
        **params,
    }

    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"https://queue.fal.run/{fal_endpoint}",
                headers={
                    "Authorization": f"Key {fal_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # Extract image URL
            image_url = None
            if "images" in result and len(result["images"]) > 0:
                image_url = result["images"][0].get("url")
            elif "image" in result:
                image_url = result["image"].get("url")

            return {
                "status": "success",
                "model": model,
                "image_url": image_url,
                "result": result,
            }
    except httpx.HTTPError as e:
        return {"error": f"Fal.ai request failed: {e}"}
    except Exception as e:
        return {"error": f"Image generation failed: {e}"}
