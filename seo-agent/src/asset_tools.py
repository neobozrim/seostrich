"""Asset generation tools — routing and model selection for image generation."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from . import memory


AGENT_NAME = "builder-agent"


# Model routing based on asset type
MODEL_ROUTING = {
    "wordmark": "ideogram-3.0",
    "logo": "ideogram-3.0",
    "icon": "recraft-v4",
    "illustration": "recraft-v4",
    "vector": "recraft-v4",
    "svg": "recraft-v4",
    "photo": "flux-2-pro",
    "photoreal": "flux-2-pro",
    "hero": "flux-2-pro",
    "background": "flux-2-pro",
    "draft": "imagen-4-fast",
    "concept": "imagen-4-fast",
    "bulk": "imagen-4-fast",
}


# Model endpoints
MODEL_ENDPOINTS = {
    "ideogram-3.0": "fal-ai/ideogram/v3",
    "recraft-v4": "fal-ai/recraft-v4",
    "flux-2-pro": "fal-ai/flux-pro/v1.1",
    "imagen-4-fast": "fal-ai/imagen4/fast",
}


def select_model(asset_type: str, commercial: bool = True) -> str:
    """Select the best model for the asset type.

    Args:
        asset_type: wordmark/logo/icon/illustration/vector/svg/photo/photoreal/hero/background/draft/concept/bulk
        commercial: whether output will be used commercially

    Returns:
        Model name
    """
    model = MODEL_ROUTING.get(asset_type.lower(), "flux-2-pro")

    # Licensing checks
    if "dev" in model.lower() and commercial:
        # FLUX dev models cannot be used commercially
        if "flux" in model:
            return "flux-2-pro"  # Upgrade to pro

    return model


def generate_asset(
    prompt: str,
    asset_type: str,
    brand_profile: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    commercial: bool = True,
) -> dict[str, Any]:
    """Generate an asset with automatic model selection and brand token injection.

    Args:
        prompt: Base prompt for image generation
        asset_type: Type of asset (wordmark/logo/icon/illustration/photo/etc)
        brand_profile: Brand profile with colors/typography/texture to inject
        params: Additional model parameters
        commercial: Whether output will be used commercially

    Returns:
        Generation result with image URL and metadata
    """
    params = params or {}

    # Select model
    model = select_model(asset_type, commercial)

    # Inject brand tokens into prompt
    if brand_profile:
        prompt = _inject_brand_tokens(prompt, brand_profile, model)

    # Check FAL_KEY
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        return {
            "error": "FAL_KEY not set. Add to .env: FAL_KEY=your_key_here",
            "hint": "Get key from: https://fal.ai/dashboard/keys",
        }

    # Build request
    endpoint = MODEL_ENDPOINTS.get(model)
    if not endpoint:
        return {"error": f"Unknown model: {model}"}

    payload = {
        "prompt": prompt,
        "commercial": commercial,
        **params,
    }

    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"https://queue.fal.run/{endpoint}",
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

            # Record to blackboard
            memory.record_learning(
                f"Generated {asset_type} asset using {model}",
                context={
                    "prompt": prompt[:100],
                    "model": model,
                    "commercial": commercial,
                },
                agent=AGENT_NAME,
            )

            return {
                "status": "success",
                "model": model,
                "asset_type": asset_type,
                "image_url": image_url,
                "result": result,
            }
    except httpx.HTTPError as e:
        return {"error": f"Fal.ai request failed: {e}"}
    except Exception as e:
        return {"error": f"Asset generation failed: {e}"}


def _inject_brand_tokens(prompt: str, brand_profile: dict[str, Any], model: str) -> str:
    """Inject brand tokens (colors, typography, texture) into the prompt."""
    injected = prompt

    # Colors
    colors = brand_profile.get("colors", {})
    if colors:
        color_list = []
        if colors.get("base"):
            color_list.append(f"base {colors['base']}")
        if colors.get("primary"):
            color_list.append(f"primary {colors['primary']}")
        if colors.get("accent"):
            color_list.append(f"accent {colors['accent']}")
        if color_list:
            injected += f". Color palette: {', '.join(color_list)}"

    # Typography style
    typography = brand_profile.get("typography", {})
    if typography:
        primary_font = typography.get("primary", {}).get("family")
        if primary_font:
            if "ideogram" in model or "recraft" in model:
                # These models can handle typography instructions
                injected += f". Typography style: {primary_font}, bold, clean"

    # Texture/grade
    texture = brand_profile.get("texture_and_grade", {})
    if texture:
        texture_desc = []
        if texture.get("temperature"):
            texture_desc.append(texture["temperature"])
        if texture.get("saturation"):
            texture_desc.append(texture["saturation"])
        if texture.get("grain"):
            texture_desc.append(texture["grain"])
        if texture_desc:
            injected += f". Style: {', '.join(texture_desc)}"

    return injected


def generate_wordmark(
    text: str,
    brand_profile: dict[str, Any],
    style: str = "bold",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a wordmark/logo with text.

    Args:
        text: Text to render (e.g., "UNBLOCKED")
        brand_profile: Brand profile with typography/colors
        style: Style hint (bold/handmade)
        params: Additional parameters

    Returns:
        Generation result
    """
    typography = brand_profile.get("typography", {})
    colors = brand_profile.get("colors", {})

    font = typography.get("primary", {}).get("family", "bold sans-serif")
    accent = colors.get("accent", "#000000")

    prompt = f"Wordmark logo: '{text}' in {font} typography, {style} style, accent color {accent}, clean, professional"

    return generate_asset(
        prompt=prompt,
        asset_type="wordmark",
        brand_profile=brand_profile,
        params=params,
        commercial=True,
    )


def generate_icon(
    concept: str,
    brand_profile: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an icon or symbol.

    Args:
        concept: Icon concept (e.g., "unlocked padlock", "rocket")
        brand_profile: Brand profile with colors
        params: Additional parameters

    Returns:
        Generation result
    """
    colors = brand_profile.get("colors", {})
    accent = colors.get("accent", "#000000")

    prompt = f"Icon: {concept}, simple, minimal, {accent} color, vector style"

    return generate_asset(
        prompt=prompt,
        asset_type="icon",
        brand_profile=brand_profile,
        params=params,
        commercial=True,
    )


def generate_hero_image(
    scene: str,
    brand_profile: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a photorealistic hero image.

    Args:
        scene: Scene description
        brand_profile: Brand profile with colors/texture
        params: Additional parameters

    Returns:
        Generation result
    """
    return generate_asset(
        prompt=scene,
        asset_type="hero",
        brand_profile=brand_profile,
        params=params,
        commercial=True,
    )


def generate_illustration(
    concept: str,
    brand_profile: dict[str, Any],
    style: str = "flat",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an illustration.

    Args:
        concept: Illustration concept
        brand_profile: Brand profile with colors
        style: Illustration style (flat/isometric/hand-drawn)
        params: Additional parameters

    Returns:
        Generation result
    """
    colors = brand_profile.get("colors", {})
    color_list = [colors.get("primary"), colors.get("accent")]
    color_list = [c for c in color_list if c]

    prompt = f"Illustration: {concept}, {style} style"
    if color_list:
        prompt += f", colors: {', '.join(color_list)}"

    return generate_asset(
        prompt=prompt,
        asset_type="illustration",
        brand_profile=brand_profile,
        params=params,
        commercial=True,
    )


def batch_generate(
    prompts: list[str],
    asset_type: str,
    brand_profile: dict[str, Any] | None = None,
    commercial: bool = True,
) -> dict[str, Any]:
    """Generate multiple assets in batch.

    Args:
        prompts: List of prompts
        asset_type: Type of assets to generate
        brand_profile: Brand profile to inject
        commercial: Whether outputs will be used commercially

    Returns:
        Batch generation results
    """
    results = []

    for prompt in prompts:
        result = generate_asset(
            prompt=prompt,
            asset_type=asset_type,
            brand_profile=brand_profile,
            commercial=commercial,
        )
        results.append(result)

    success_count = sum(1 for r in results if r.get("status") == "success")

    return {
        "status": "success" if success_count > 0 else "failed",
        "total": len(prompts),
        "success": success_count,
        "failed": len(prompts) - success_count,
        "results": results,
    }
