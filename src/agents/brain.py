"""The Brain — OracleForge AI processing agents.

Uses DeepSeek Flash via OpenRouter to:

- Analyze trends and identify top narratives
- Generate Twitter/X social content in ChadSatoshi's voice
- Generate replies to @mentions / celebrity posts
- Write the weekly newsletter ("The Degen Dispatch")
- Refresh ChadSatoshi's style guide weekly

Design:
- All prompts come from ``config/prompts.yaml`` (no hardcoded prompts here).
- Calls use the OpenRouter chat completions API with retry + fallback model.
- If the API fails, returns cached/fallback content so pipelines keep moving.
- Logs financial cost of each call to financial_records.

CLI:
    python main.py --run-brain [--mode analysis|social|newsletter|voice_refresh]
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from .. import config
from ..logger import get_logger
from ..utils import safe_json, utcnow

log = get_logger("brain")

#: OpenRouter chat completions endpoint
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

#: Cost estimate per 1k tokens (DeepSeek Flash pricing approx; used for tracking)
COST_PER_1K_INPUT = 0.0002
COST_PER_1K_OUTPUT = 0.0004


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> str:
    """Load a prompt template from prompts.yaml.

    Args:
        name: Key in prompts.yaml (e.g. "trend_analysis").

    Returns:
        The template string.

    Raises:
        KeyError if the template does not exist.
    """
    prompts = config.prompts()
    if name not in prompts:
        raise KeyError(f"Prompt template '{name}' not found in prompts.yaml")
    return prompts[name]


def chadsatoshi_prompt() -> str:
    """Return the ChadSatoshi system prompt.

    Returns:
        The system prompt string from prompts.yaml.
    """
    return load_prompt("chadsatoshi_system")


# ---------------------------------------------------------------------------
# OpenRouter client
# ---------------------------------------------------------------------------

async def chat_completion(
    session: aiohttp.ClientSession,
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.8,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call OpenRouter chat completions with retry + fallback model.

    Args:
        session: aiohttp session.
        system_prompt: System/voice prompt.
        user_prompt: User prompt with data.
        model: Model ID (defaults to OPENROUTER_MODEL env).
        temperature: Sampling temperature.
        max_tokens: Max output tokens.

    Returns:
        Dict: {"text": str, "model": str, "cost": float}.

    Raises:
        RuntimeError if all attempts fail.
    """
    model = model or config.env("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    fallback = config.env("OPENROUTER_FALLBACK_MODEL", "deepseek/deepseek-chat")
    api_key = config.env("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.env("SITE_URL", "http://localhost:5000"),
        "X-Title": "OracleForge",
    }

    async def _call(mdl: str) -> Dict[str, Any]:
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with session.post(
            OPENROUTER_URL, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            resp.raise_for_status()
            body = await resp.json()

        usage = body.get("usage", {}) or {}
        in_tokens = usage.get("prompt_tokens", 0) or 0
        out_tokens = usage.get("completion_tokens", 0) or 0
        cost = (in_tokens / 1000) * COST_PER_1K_INPUT + (out_tokens / 1000) * COST_PER_1K_OUTPUT

        content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        content = content.strip()
        if not content:
            raise RuntimeError(f"Empty response from {mdl}")

        return {"text": content, "model": mdl, "cost": cost}

    # First attempt with primary model
    try:
        return await _call(model)
    except Exception as exc:  # noqa: BLE001
        log.warning("Primary model %s failed: %s — trying fallback %s", model, exc, fallback)

    # Fallback attempt
    if fallback != model:
        try:
            return await _call(fallback)
        except Exception as exc:  # noqa: BLE001
            log.error("Fallback model %s also failed: %s", fallback, exc)

    raise RuntimeError("All OpenRouter attempts failed")


# ---------------------------------------------------------------------------
# Task implementations
# ---------------------------------------------------------------------------

async def analyze_trends(db: Any, session: aiohttp.ClientSession, limit: int = 20) -> Dict[str, Any]:
    """Analyze recent trends and identify top narratives.

    Args:
        db: Database instance.
        session: aiohttp session.
        limit: Max trends to feed the model.

    Returns:
        Dict with narrative analysis (or fallback summary).
    """
    trends = db.latest_trends(limit=limit)
    if not trends:
        log.info("No trends in DB — analysis skipped")
        return {"narratives": [], "red_flags": [], "summary": "No data available yet."}

    # Build a compact, token-friendly data summary
    lines = []
    for t in trends:
        lines.append(
            f"{t['source']}: {t['token_symbol']} ({t['token_name']}) "
            f"price={t['price']} chg={t['price_change_pct']}% vol={t['volume_24h']} "
            f"mcap={t['market_cap']} rank={t['rank']} url={t['url']}"
        )
    data = "\n".join(lines)

    prompt = load_prompt("trend_analysis").format(data=data)

    try:
        result = await chat_completion(
            session,
            "You are The Brain of OracleForge, a precise meme-coin market analyst that only uses provided data.",
            prompt,
            temperature=0.4,
            max_tokens=1200,
        )
        # Log financial cost
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain trend_analysis ({result.get('model', '')})")
        parsed = safe_json(result.get("text", ""))
        if parsed and isinstance(parsed, dict):
            return parsed
        return {"narratives": [], "red_flags": [], "summary": result.get("text", "")}
    except Exception as exc:  # noqa: BLE001
        log.error("Trend analysis failed: %s", exc)
        return fallback_analysis(trends)


def fallback_analysis(trends: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Local heuristic fallback when the API is unavailable.

    Picks the top movers from the trend data as pseudo-narratives.

    Args:
        trends: Trend rows from DB.

    Returns:
        Dict with narratives, red_flags, summary.
    """
    movers = sorted(
        [t for t in trends if t.get("price_change_pct")],
        key=lambda t: t["price_change_pct"], reverse=True,
    )[:3]
    narratives = [
        {
            "name": f"{t['token_symbol']} momentum",
            "tokens": [t["token_symbol"]],
            "peak_window": "next 6-24 hours",
            "confidence": 5,
            "insight": f"{t['token_symbol']} up {t['price_change_pct']}% — speculative momentum, DYOR.",
        }
        for t in movers
    ]
    red_flags = [
        "High volatility: use risk management.",
        "Meme coins can move -50%+ as fast as +50%.",
    ]
    summary = f"Analyzed {len(trends)} trends locally (AI API unavailable). " \
              "No financial advice — just vibes and data."
    return {"narratives": narratives, "red_flags": red_flags, "summary": summary}


async def generate_social_posts(db: Any, session: aiohttp.ClientSession,
                                limit: int = 10) -> List[str]:
    """Generate 3 ChadSatoshi posts for The Radar.

    Args:
        db: Database instance.
        session: aiohttp session.
        limit: Max trends to include.

    Returns:
        List of post strings (falls back to templates on API failure).
    """
    trends = db.latest_trends(limit=limit)
    if not trends:
        return []

    data = "\n".join(
        f"{t['token_symbol']}: {t['price_change_pct']}% in 24h (source: {t['source']})"
        for t in trends[:10]
    )
    prompt = load_prompt("social_content").format(data=data)

    try:
        result = await chat_completion(
            session, chadsatoshi_prompt(), prompt, temperature=0.9, max_tokens=600,
        )
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain social_content ({result.get('model', '')})")
        posts = [line.strip() for line in result.get("text", "").splitlines() if line.strip()]
        return posts[:3] if posts else [result.get("text", "")]
    except Exception as exc:  # noqa: BLE001
        log.error("Social content generation failed: %s", exc)
        return fallback_social_posts(trends)


def fallback_social_posts(trends: List[Dict[str, Any]]) -> List[str]:
    """Generate template posts if the API is down.

    Args:
        trends: Trend rows.

    Returns:
        List of 3 post strings.
    """
    posts = []
    movers = sorted(
        [t for t in trends if t.get("price_change_pct")],
        key=lambda t: t["price_change_pct"], reverse=True,
    )[:3]
    if movers:
        t = movers[0]
        posts.append(
            f"🚨 TREND ALERT: ${t['token_symbol']} up {t['price_change_pct']}%! "
            "Screenshot or it didn't happen. Full breakdown in The Radar Pro. 🚀"
        )
    if len(movers) > 1:
        t = movers[1]
        posts.append(
            f"👀 Watching ${t['token_symbol']} closely. Volume is spicy. "
            "Not financial advice — just the matrix talking. 🧠"
        )
    posts.append(
        "We forge the memes. You ride the waves. 🌊 "
        "OracleForge AI analyzing the memecoin matrix 24/7. Follow for alpha. 🔥"
    )
    return posts[:3]


async def create_reply(db: Any, session: aiohttp.ClientSession,
                       post_text: str, user_handle: str) -> str:
    """Generate a ChadSatoshi reply to a mention/comment.

    Args:
        db: Database instance.
        session: aiohttp session.
        post_text: The post being replied to.
        user_handle: The user who posted.

    Returns:
        Reply text.
    """
    prompt = load_prompt("reply_generation").format(
        post_text=post_text, user_handle=user_handle,
    )
    try:
        result = await chat_completion(
            session, chadsatoshi_prompt(), prompt, temperature=0.9, max_tokens=220,
        )
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain reply ({result.get('model', '')})")
        return result.get("text", "") or "Ayyy that's what we like to see! 🚀"
    except Exception as exc:  # noqa: BLE001
        log.error("Reply generation failed: %s", exc)
        return "Ayyy that's what we like to see! 🚀 Not financial advice, just vibes."


async def generate_newsletter(db: Any, session: aiohttp.ClientSession) -> Dict[str, str]:
    """Generate the weekly newsletter in ChadSatoshi's voice.

    Args:
        db: Database instance.
        session: aiohttp session.

    Returns:
        Dict: {"subject": str, "body": str, "text": full text}.
    """
    trends = db.latest_trends(limit=15)
    data = "\n".join(
        f"{t['token_symbol']}: {t['price_change_pct']}% "
        f"(volume ${(t['volume_24h'] or 0):,.0f})"
        for t in trends[:15]
    ) if trends else "This week was quiet — no major data captured."

    week = datetime.now(timezone.utc).isocalendar().week
    prompt = load_prompt("newsletter").format(data=data, week=week)

    try:
        result = await chat_completion(
            session, chadsatoshi_prompt(), prompt, temperature=0.9, max_tokens=1200,
        )
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain newsletter ({result.get('model', '')})")
        text = result.get("text", "")
        # First line = subject (ALL CAPS convention)
        lines = text.strip().splitlines()
        subject = lines[0].strip() if lines else "THE DEGEN DISPATCH"
        body = "\n".join(lines[1:]).strip()
        return {"subject": subject, "body": body, "text": text}
    except Exception as exc:  # noqa: BLE001
        log.error("Newsletter generation failed: %s", exc)
        subject = "THE DEGEN DISPATCH - VOLUME STILL GOES UP"
        body = (
            "gm anon!\n\n"
            "This week the matrix glitched in the best way. Meme coins swung "
            "wild while the rest of the world slept. We tracked it all.\n\n"
            "This is a cached/fallback newsletter while the AI API was offline. "
            "The real one returns when the forge is hot again.\n\n"
            "Not financial advice. Just vibes and data. 🚀\n\n"
            "- ChadSatoshi"
        )
        return {"subject": subject, "body": body, "text": f"{subject}\n\n{body}"}


async def generate_linkedin_post(db: Any, session: aiohttp.ClientSession) -> str:
    """Generate the weekly LinkedIn B2B post.

    Args:
        db: Database instance.
        session: aiohttp session.

    Returns:
        Post text (or fallback).
    """
    trends = db.latest_trends(limit=8)
    data = "\n".join(
        f"{t['token_symbol']}: {t['price_change_pct']}% "
        f"(volume ${(t['volume_24h'] or 0):,.0f})"
        for t in trends[:8]
    ) if trends else "Data pipeline quiet this week."

    prompt = load_prompt("linkedin_post").format(data=data)
    try:
        result = await chat_completion(
            session, chadsatoshi_prompt(), prompt, temperature=0.8, max_tokens=700,
        )
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain linkedin_post ({result.get('model', '')})")
        return result.get("text", "")
    except Exception as exc:  # noqa: BLE001
        log.error("LinkedIn post generation failed: %s", exc)
        return ""


async def refresh_voice(db: Any, session: aiohttp.ClientSession) -> str:
    """Refresh ChadSatoshi's style from recent trending posts.

    Args:
        db: Database instance.
        session: aiohttp session.

    Returns:
        The updated style guide (stored in settings).
    """
    trending = db.latest_posts(limit=10, status="posted") or db.latest_posts(limit=10)
    sample = "\n".join(
        f"[{p['platform']}] {p['content'][:200]}" for p in trending
    ) or "No recent posts available yet."

    prompt = load_prompt("voice_reprompt").format(trending_posts=sample)
    try:
        result = await chat_completion(
            session, chadsatoshi_prompt(), prompt, temperature=0.9, max_tokens=800,
        )
        db.add_financial("cost", "openrouter", float(result.get("cost", 0)),
                         f"Brain voice_refresh ({result.get('model', '')})")
        style = result.get("text", "")
        db.set_setting("chadsatoshi_style", style)
        log.info("Voice refreshed (%d chars)", len(style))
        return style
    except Exception as exc:  # noqa: BLE001
        log.error("Voice refresh failed: %s", exc)
        return "Voice refresh unavailable — keeping existing style."


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_brain(mode: str = "analysis", limit: int = 20,
                    session: Optional[aiohttp.ClientSession] = None,
                    db: Any = None) -> Any:
    """Run a Brain task.

    Args:
        mode: analysis | social | newsletter | voice_refresh.
        limit: Max trends to feed analysis/social modes.
        session: Optional shared aiohttp session.
        db: Optional Database instance.

    Returns:
        Task-dependent result.
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    async with session or aiohttp.ClientSession() as own_session:  # type: ignore[union-attr]
        s = own_session

        if mode == "analysis":
            return await analyze_trends(db, s, limit)
        if mode == "social":
            posts = await generate_social_posts(db, s, limit)
            for post in posts:
                db.create_post("twitter", post, post_type="radar", status="draft")
            log.info("Brain: %d social posts drafted", len(posts))
            return posts
        if mode == "newsletter":
            result = await generate_newsletter(db, s)
            full = result["text"]
            db.create_post("newsletter", full, post_type="newsletter", status="draft")
            db.set_setting("latest_newsletter_subject", result["subject"])
            log.info("Brain: newsletter generated — subject: %s", result["subject"])
            return result
        if mode == "voice_refresh":
            return await refresh_voice(db, s)

        log.error("Unknown brain mode: %s", mode)
        return None