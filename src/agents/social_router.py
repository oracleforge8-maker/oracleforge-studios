"""Social router — dispatches autonomous social runs by platform.

Allows ``main.py --run-social --platform X [--dry-run]`` to reach any of:

- twitter  → social_twitter.run_twitter (radar posts, replies, follow,
             celebrity engagement)
- discord  → social_discord.run_discord (trend radar, alpha chat,
             announcements)
- linkedin → social_linkedin.run_linkedin (weekly B2B post)

A platform failure is isolated — other platforms keep working.
"""

from __future__ import annotations

from typing import Any, Optional

from ..logger import get_logger

log = get_logger("social_router")


async def run_social(platform: str = "twitter", dry_run: bool = True,
                     db: Any = None, mode: str = "") -> int:
    """Route to the requested social platform agent.

    Args:
        platform: twitter | discord | linkedin.
        dry_run: If True, mock/dry-run mode (no external API calls).
        db: Optional Database instance.
        mode: Optional twitter sub-mode (radar_posts, replies, follow,
              celebrity_engagement). Defaults to radar_posts.

    Returns:
        Count of actions taken (posts/replies/messages).
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    platform = platform.lower()

    if platform == "twitter":
        from .social_twitter import run_twitter
        target_mode = mode or "radar_posts"
        return await run_twitter(target_mode, db=db, dry_run=dry_run)

    if platform == "discord":
        from .social_discord import run_discord
        return await run_discord(db=db, dry_run=dry_run)

    if platform == "linkedin":
        from .social_linkedin import run_linkedin
        return await run_linkedin(db=db, dry_run=dry_run)

    log.error("Unknown social platform: %s", platform)
    return 0