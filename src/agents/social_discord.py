"""Discord social agent — OracleForge community autopilot.

Autonomous behaviors:
1. Auto-post Scout trend data to #trend-radar
2. Auto-post ChadSatoshi's comments to #alpha-chat
3. Post announcements to #announcements
4. Call out welcome message for new members

Design:
- Uses discord.py when DISCORD_BOT_TOKEN is configured.
- In mock mode (no token), simulates posts to the DB for the Live Demo.
- Channel targets map from env vars:
  DISCORD_CHANNEL_TREND_RADAR, DISCORD_CHANNEL_ALPHA_CHAT,
  DISCORD_CHANNEL_ANNOUNCEMENTS.

CLI:
    python main.py --run-social --platform discord [--dry-run]
"""

from __future__ import annotations

from typing import Any, List, Optional

from .. import config
from ..logger import get_logger

log = get_logger("social_discord")


def has_credentials() -> bool:
    """Check whether a Discord bot token is configured.

    Returns:
        True if DISCORD_BOT_TOKEN is set.
    """
    return bool(config.env("DISCORD_BOT_TOKEN"))


def _channel_id(key: str) -> Optional[str]:
    """Read a channel ID from env (empty string -> None).

    Args:
        key: Env var name.

    Returns:
        Channel ID string or None.
    """
    return config.env(key) or None


# ---------------------------------------------------------------------------
# Post builders
# ---------------------------------------------------------------------------

def build_trend_radar_message(db: Any) -> str:
    """Build a #trend-radar message from the latest trends.

    Args:
        db: Database instance.

    Returns:
        Message text (plain text w/ emojis for Discord).
    """
    trends = db.latest_trends(limit=8)
    if not trends:
        return "📡 No trends captured yet. The Scout is standing by..."

    lines = ["📡 **ORACLEFORGE TREND RADAR**", ""]
    for t in trends:
        symbol = t["token_symbol"]
        change = t["price_change_pct"] or 0.0
        arrow = "🟢" if change >= 0 else "🔴"
        lines.append(f"{arrow} **${symbol}** {change:+.1f}% (source: {t['source']})")
    lines.append("")
    lines.append("> Not financial advice. Just vibes and data. 🚀")
    return "\n".join(lines)


def build_alpha_chat_message(db: Any) -> str:
    """Build a #alpha-chat message (latest drafted radar post).

    Args:
        db: Database instance.

    Returns:
        Message text.
    """
    posts = db.latest_posts(limit=3, platform="twitter", status="posted")
    if posts:
        return f"🤖 **ChadSatoshi says:** {posts[0]['content']}"
    return "🤖 ChadSatoshi is calibrating the matrix... hold tight, anon."


def build_announcement(db: Any) -> str:
    """Build an announcements message.

    Args:
        db: Database instance.

    Returns:
        Announcement text.
    """
    return (
        "🔥 **ORACLEFORGE LIVE** 🔥\n"
        "We forge the memes. You ride the waves. 🌊\n"
        "Join the waitlist at oracleforge.ai to get The Radar Pro free "
        "for your first month (first 100 only!).\n"
        "Refer 3 friends → permanent Pro access for life. 💎🙌"
    )


# ---------------------------------------------------------------------------
# Posting helpers
# ---------------------------------------------------------------------------

def _post_mock(db: Any, channel: str, content: str) -> None:
    """Log a mock Discord post to the DB.

    Args:
        db: Database instance.
        channel: Target channel name.
        content: Message content.
    """
    db.create_post("discord", content, post_type=channel, status="mock")
    log.info("[mock] Discord #%s: %s", channel, content[:100])


async def _post_live(channel_id: str, content: str) -> bool:
    """Send a message to a Discord channel.

    Args:
        channel_id: Discord channel snowflake.
        content: Message text.

    Returns:
        True on success, False on failure.
    """
    import discord

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    sent = False

    @client.event
    async def on_ready() -> None:  # type: ignore[override]
        nonlocal sent
        try:
            channel = client.get_channel(int(channel_id))
            if channel is None:
                log.error("Discord channel %s not found", channel_id)
            else:
                await channel.send(content)
                sent = True
                log.info("Discord message sent to channel %s", channel_id)
        except Exception as exc:  # noqa: BLE001
            log.error("Discord send failed: %s", exc)
        finally:
            await client.close()

    await client.start(config.env("DISCORD_BOT_TOKEN"))
    return sent


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_discord(db: Any = None, dry_run: bool = True) -> int:
    """Run the Discord autopilot: post trend/alphas/announcements.

    Args:
        db: Optional Database instance.
        dry_run: If True, mock mode (log only).

    Returns:
        Number of messages sent/queued.
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    log.info("Discord agent running (dry_run=%s)", dry_run)
    count = 0

    # 1) #trend-radar
    radar_msg = build_trend_radar_message(db)
    radar_channel = _channel_id("DISCORD_CHANNEL_TREND_RADAR")
    if radar_channel and not dry_run and has_credentials():
        if await _post_live(radar_channel, radar_msg):
            count += 1
    else:
        _post_mock(db, "trend-radar", radar_msg)
        count += 1

    # 2) #alpha-chat
    alpha_msg = build_alpha_chat_message(db)
    alpha_channel = _channel_id("DISCORD_CHANNEL_ALPHA_CHAT")
    if alpha_channel and not dry_run and has_credentials():
        if await _post_live(alpha_channel, alpha_msg):
            count += 1
    else:
        _post_mock(db, "alpha-chat", alpha_msg)
        count += 1

    # 3) #announcements
    ann_msg = build_announcement(db)
    ann_channel = _channel_id("DISCORD_CHANNEL_ANNOUNCEMENTS")
    if ann_channel and not dry_run and has_credentials():
        if await _post_live(ann_channel, ann_msg):
            count += 1
    else:
        _post_mock(db, "announcements", ann_msg)
        count += 1

    log.info("Discord complete: %d messages", count)
    return count