"""The Forge — OracleForge image generation agent.

Generates marketing/branding/meme images via DALL-E 3 (OpenAI):

- **business** — professional crypto marketing image for a featured coin
- **meme**     — energetic community hype image with a fun quote
- **brand**    — OracleForge corporate AI branding (oracle eye + forge hammer)

Design:
- Prompts come from ``config/prompts.yaml`` (template-based).
- If OpenAI is not configured, falls back to generating a branded SVG/PNG
  placeholder with the OracleForge palette (dark #0A0A0A, purple #2D1B69,
  neon green #00FF88) so the feature always works in demo mode.
- Saves images to ``data/images/`` and returns the file path.

CLI:
    python main.py --run-forge --type brand
    python main.py --run-forge --type business --coin "MoonCoin"
    python main.py --run-forge --type meme --quote "TO THE MOON"
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from .. import config
from ..logger import get_logger
from ..utils import slugify, utcnow

log = get_logger("forge")

#: Output directory for generated images
IMAGES_DIR = config.PROJECT_ROOT / "data" / "images"

#: Brand palette
PALETTE = {
    "purple": "#2D1B69",
    "green": "#00FF88",
    "dark": "#0A0A0A",
    "silver": "#C0C0C0",
    "white": "#FFFFFF",
}


def _images_dir() -> Path:
    """Ensure and return the images output directory.

    Returns:
        Path to data/images/ (created if missing).
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGES_DIR


def load_forge_prompt(name: str, **kwargs: str) -> str:
    """Load and format a Forge prompt template from prompts.yaml.

    Args:
        name: Template key (forge_business_prompt, forge_meme_prompt, forge_brand_prompt).
        **kwargs: Template variables.

    Returns:
        Formatted prompt string.
    """
    prompts = config.prompts()
    template = prompts[name]
    return template.format(**kwargs)


def has_openai_key() -> bool:
    """Check whether OpenAI is configured for DALL-E.

    Returns:
        True if OPENAI_API_KEY is set.
    """
    return bool(config.env("OPENAI_API_KEY"))


# ---------------------------------------------------------------------------
# DALL-E 3 generation
# ---------------------------------------------------------------------------

async def generate_with_dalle(prompt: str, image_type: str) -> Path:
    """Generate an image using DALL-E 3.

    Args:
        prompt: The formatted image prompt.
        image_type: brand | business | meme (used in filename).

    Returns:
        Path to the saved image file.

    Raises:
        RuntimeError if generation fails.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=config.env("OPENAI_API_KEY"))
    model = config.env("OPENAI_IMAGE_MODEL", "dall-e-3")
    size = config.env("OPENAI_IMAGE_SIZE", "1024x1024")
    quality = config.env("OPENAI_IMAGE_QUALITY", "standard")

    log.info("DALL-E 3 generating %s image (%s, %s)...", image_type, model, size)
    resp = await client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    url = resp.data[0].url if resp.data else None
    if not url:
        raise RuntimeError("DALL-E returned no image URL")

    # Download the generated image
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as image_resp:
            image_resp.raise_for_status()
            content = await image_resp.read()

    filename = f"forge_{image_type}_{slugify(utcnow())}.png"
    out_path = _images_dir() / filename
    out_path.write_bytes(content)
    log.info("DALL-E image saved: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# SVG fallback (no OpenAI key)
# ---------------------------------------------------------------------------

def _svg_template(kind: str, title: str, subtitle: str) -> str:
    """Build a branded SVG placeholder.

    Args:
        kind: image type slug.
        title: Main display text.
        subtitle: Secondary display text.

    Returns:
        SVG document string.
    """
    eye = """
    <circle cx="420" cy="220" r="80" fill="none" stroke="#00FF88" stroke-width="6"/>
    <circle cx="420" cy="220" r="40" fill="#00FF88" opacity="0.25"/>
    <path d="M280 320 Q420 160 560 320 Q420 300 280 320"
          fill="none" stroke="#00FF88" stroke-width="5"/>
    """
    hammer = """
    <rect x="680" y="160" width="50" height="160" rx="10" fill="#C0C0C0"/>
    <path d="M650 120 h110 v40 h-110 z" fill="#C0C0C0"/>
    <circle cx="705" cy="250" r="8" fill="#00FF88"/>
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0A0A0A"/>
      <stop offset="100%" stop-color="#2D1B69"/>
    </linearGradient>
    <style>
      .title {{ font-family: Arial, sans-serif; font-weight: bold; fill: #FFFFFF; font-size: 64px; }}
      .sub   {{ font-family: Arial, sans-serif; fill: #00FF88; font-size: 28px; }}
      .tag   {{ font-family: Arial, sans-serif; fill: #C0C0C0; font-size: 22px; }}
    </style>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  <rect x="24" y="24" width="976" height="976" rx="32" fill="none" stroke="#00FF88" stroke-opacity="0.35" stroke-width="2"/>
  {eye if kind == 'brand' else hammer if kind == 'business' else hammer}
  <text x="512" y="760" text-anchor="middle" class="title">{title}</text>
  <text x="512" y="840" text-anchor="middle" class="sub">{subtitle}</text>
  <text x="512" y="930" text-anchor="middle" class="tag">OracleForge • We forge the memes. You ride the waves.</text>
</svg>"""


def generate_svg_fallback(image_type: str, coin: str = "", quote: str = "") -> Path:
    """Create a branded SVG placeholder image.

    Args:
        image_type: brand | business | meme.
        coin: Coin name for business images.
        quote: Fun quote for meme images.

    Returns:
        Path to the saved SVG file.
    """
    if image_type == "business":
        title = (coin or "YOUR COIN").upper()
        subtitle = "BULLISH • NFA"
    elif image_type == "meme":
        title = (quote or "TO THE MOON").upper()
        subtitle = "MEME COIN SEASON 🔥"
    else:  # brand
        title = "ORACLEFORGE"
        subtitle = "THE EYE FORGES THE WAVE"

    svg = _svg_template(image_type, title, subtitle)
    filename = f"forge_{image_type}_placeholder_{slugify(utcnow())}.svg"
    out_path = _images_dir() / filename
    out_path.write_text(svg, encoding="utf-8")

    # Also render a PNG via Pillow for easy preview
    try:
        from PIL import Image, ImageDraw, ImageFont
        png_path = _render_png_from_svg(out_path, image_type, title, subtitle)
        log.info("SVG fallback saved: %s (+PNG: %s)", out_path.name, png_path.name)
        return png_path
    except Exception as exc:  # noqa: BLE001 — SVG alone is still usable
        log.warning("PNG render skipped: %s", exc)
        return out_path


def _render_png_from_svg(svg_path: Path, kind: str, title: str, subtitle: str) -> Path:
    """Render a simple branded PNG using Pillow (no cairosvg dependency).

    Args:
        svg_path: Source SVG (kept for archival).
        kind: Image type slug.
        title: Main text.
        subtitle: Secondary text.

    Returns:
        Path to the generated PNG.
    """
    from PIL import Image, ImageDraw, ImageFont

    size = (1024, 1024)
    img = Image.new("RGB", size, "#0A0A0A")
    draw = ImageDraw.Draw(img)

    # Vertical gradient approximation (dark -> purple)
    for y in range(size[1]):
        t = y / size[1]
        r = int(10 + (45 - 10) * t)
        g = int(10 + (27 - 10) * t)
        b = int(10 + (105 - 10) * t)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))

    # Border
    draw.rectangle([24, 24, size[0] - 24, size[1] - 24], outline="#00FF88", width=3)

    # Central emblem: simple eye + hammer glyph
    cx, cy = size[0] // 2, size[1] // 2 - 160
    draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline="#00FF88", width=8)
    draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill="#00FF88")

    # Title / subtitle
    try:
        font_title = ImageFont.truetype("arial.ttf", 72)
        font_sub = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((cx, 760), title, fill="#FFFFFF", font=font_title, anchor="mm")
    draw.text((cx, 850), subtitle, fill="#00FF88", font=font_sub, anchor="mm")
    draw.text((cx, 940), "OracleForge • We forge the memes. You ride the waves.",
              fill="#C0C0C0", font=font_sub, anchor="mm")

    png_path = svg_path.with_suffix(".png")
    img.save(png_path, "PNG")
    return png_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_forge(image_type: str = "brand", coin: str = "", quote: str = "") -> Path:
    """Generate an image (DALL-E 3 or SVG fallback).

    Args:
        image_type: brand | business | meme.
        coin: Coin name for business images.
        quote: Fun quote for meme images.

    Returns:
        Path to the generated image.
    """
    _images_dir()

    if image_type not in {"brand", "business", "meme"}:
        log.warning("Unknown image type '%s' — defaulting to brand", image_type)
        image_type = "brand"

    if image_type == "business":
        prompt = load_forge_prompt("forge_business_prompt", coin_name=coin or "Your Coin")
    elif image_type == "meme":
        prompt = load_forge_prompt("forge_meme_prompt", fun_quote=quote or "TO THE MOON")
    else:
        prompt = load_forge_prompt("forge_brand_prompt")

    log.info("Forge: building %s image", image_type)

    if has_openai_key():
        try:
            path = await generate_with_dalle(prompt, image_type)
            print(f"🎨 Image generated (DALL-E 3): {path}")
            return path
        except Exception as exc:  # noqa: BLE001 — fall back to SVG
            log.error("DALL-E generation failed (%s) — falling back to SVG", exc)

    log.info("Using branded SVG/PNG fallback (no OpenAI key configured)")
    path = generate_svg_fallback(image_type, coin=coin, quote=quote)
    print(f"🎨 Image generated (placeholder): {path}")
    return path