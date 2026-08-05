"""LinkedIn social agent — weekly B2B posts for The Forge.

Autonomous behavior:
- Posts a weekly professional AI/Web3 insight post (cron: Friday or per
  schedule.yaml ``linkedin_post``). Targets B2B clients for The Forge
  (white-label meme coin launches & intelligence).

Design:
- Uses the LinkedIn API (v2) when credentials are present.
- In mock mode (no credentials), generates via The Brain's templates and
  logs the post to the DB with status "mock".
- Content generation uses the ``linkedin_post`` prompt template + data.

CLI:
    python main.py --run-social --platform linkedin [--dry-run]
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..logger import get_logger

log = get_logger("social_linkedin")


def has_credentials() -> bool:
    """Check whether a LinkedIn access token is configured.

    Returns:
        True if LINKEDIN_ACCESS_TOKEN is set.
    """
    return bool(config.env("LINKEDIN_ACCESS_TOKEN"))


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

async def build_linkedin_post(db: Any) -> str:
    """Build the weekly B2B post (AI-generated with fallback).

    Args:
        db: Database instance.

    Returns:
        Post text.
    """
    import aiohttp
    from .brain import generate_linkedin_post as brain_linkedin

    try:
        async with aiohttp.ClientSession() as session:
            post = await brain_linkedin(db, session)
        return post or _fallback_post(db)
    except Exception as exc:  # noqa: BLE001
        log.warning("LinkedIn AI generation failed (%s) — using template", exc)
        return _fallback_post(db)


def _fallback_post(db: Any) -> str:
    """Branded fallback post when the AI API is unavailable.

    Args:
        db: Database instance (for subscriber count flavor).

    Returns:
        Post text.
    """
    count = db.subscriber_count()
    return (
        "The intersection of AI and Web3 is producing something unprecedented: "
        "autonomous intelligence agents that never sleep, never FOMO, and never "
        "make emotional decisions.\n\n"
        "At OracleForge, we built an AI studio that tracks meme-coin culture in "
        "real time — scraping trends, analyzing narratives, and generating "
        "community-first content across the entire social stack.\n\n"
        f"Early signal: our waitlist just crossed {count} builders, and the "
        "patterns we're seeing in narrative velocity are fascinating.\n\n"
        "For teams exploring token launches, our B2B arm (The Forge) offers "
        "white-label intelligence. One question for you:\n\n"
        "What's the most underrated AI use case in Web3 right now? 👇"
    )


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def post_linkedin(db: Any, content: str, dry_run: bool = True) -> int:
    """Post or mock a LinkedIn update.

    Args:
        db: Database instance.
        content: Post text.
        dry_run: If True, mock mode.

    Returns:
        Post row id.
    """
    post_id = db.create_post(
        "linkedin", content, post_type="b2b",
        status="mock" if (dry_run or not has_credentials()) else "draft",
    )

    if dry_run or not has_credentials():
        log.info("[mock] LinkedIn B2B post: %s", content[:120])
        db.mark_post_posted(post_id, external_id=f"mock-li-{post_id}")
        return post_id

    try:
        # LinkedIn v2 API requires OAuth2 Service principal posting flow.
        # We use the REST endpoint with the configured access token.
        import requests

        url = "https://api.linkedin.com/v2/ugcPosts"
        headers = {
            "Authorization": f"Bearer {config.env('LINKEDIN_ACCESS_TOKEN')}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        author_urn = config.env("LINKEDIN_ORGANIZATION_ID")
        if not author_urn:
            raise RuntimeError("LINKEDIN_ORGANIZATION_ID not set")

        payload = {
            "author": f"urn:li:organization:{author_urn}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        post_urn = resp.json().get("id", "")
        db.mark_post_posted(post_id, external_id=post_urn)
        log.info("LinkedIn post published (URN %s)", post_urn)
    except Exception as exc:  # noqa: BLE001
        log.error("LinkedIn post failed: %s", exc)
        db.execute("UPDATE posts SET status='failed' WHERE id=?", (post_id,))

    return post_id


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_linkedin(db: Any = None, dry_run: bool = True) -> int:
    """Run the weekly LinkedIn B2B post.

    Args:
        db: Optional Database instance.
        dry_run: If True, mock mode.

    Returns:
        Post row id (or 0).
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    log.info("LinkedIn agent running (dry_run=%s)", dry_run)
    content = await build_linkedin_post(db)
    return post_linkedin(db, content, dry_run=dry_run)
