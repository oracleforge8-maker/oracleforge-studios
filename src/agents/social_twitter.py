"""Twitter/X social agent — The Radar's primary mouthpiece.

Autonomous behaviors:
1. **radar_posts** — 3 daily posts with factual trend data (The Radar free tier)
2. **replies**     — scan @mentions every 2 hours, reply with ChadSatoshi voice
3. **follow**      — follow TWITTER_DAILY_FOLLOW_LIMIT accounts by crypto keywords
4. **celebrity_engagement** — comment on scraped celebrity posts

Design:
- Uses tweepy (X API v2) when credentials are present.
- In dry-run/mock mode (no credentials), generates posts via The Brain's
  fallback templates and logs them to the DB without sending.
- Every action is recorded in the `posts` / `replies` tables so the website
  Live Demo and The Chronicler see everything.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import aiohttp

from .. import config
from ..logger import get_logger

log = get_logger("social_twitter")


def has_credentials() -> bool:
    """Check whether full Twitter/X API credentials are configured.

    Returns:
        True if API key + secret + access token + secret are all set.
    """
    return bool(
        config.env("TWITTER_API_KEY")
        and config.env("TWITTER_API_SECRET")
        and config.env("TWITTER_ACCESS_TOKEN")
        and config.env("TWITTER_ACCESS_SECRET")
    )


def make_client() -> Any:
    """Create a tweepy Client for API v2.

    Returns:
        Configured tweepy.Client.

    Raises:
        RuntimeError if credentials are missing.
    """
    import tweepy
    return tweepy.Client(
        consumer_key=config.env("TWITTER_API_KEY"),
        consumer_secret=config.env("TWITTER_API_SECRET"),
        access_token=config.env("TWITTER_ACCESS_TOKEN"),
        access_token_secret=config.env("TWITTER_ACCESS_SECRET"),
        bearer_token=config.env("TWITTER_BEARER_TOKEN") or None,
    )


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def post_tweet(db: Any, content: str, dry_run: bool = True,
               post_type: str = "radar") -> Optional[int]:
    """Post a single tweet (or mock it).

    Args:
        db: Database instance.
        content: Tweet text.
        dry_run: If True, mock mode (log only, don't send).
        post_type: radar | engagement | celebrity | b2b.

    Returns:
        Post row id.
    """
    post_id = db.create_post("twitter", content, post_type=post_type,
                             status="mock" if dry_run else "draft")
    if len(content) > 280:
        log.warning("Tweet length %d > 280 — truncated", len(content))
        content = content[:277] + "..."

    if dry_run or not has_credentials():
        mode = "dry-run(mock)" if dry_run else "mock(no creds)"
        log.info("[%s] Tweet (%s): %s", mode, post_type, content[:120])
        db.mark_post_posted(post_id, external_id=f"mock-{post_id}")
        return post_id

    try:
        client = make_client()
        resp = client.create_tweet(text=content)
        tweet_id = resp.data["id"] if resp.data else ""
        db.mark_post_posted(post_id, external_id=tweet_id)
        log.info("Tweet posted: %s (id=%s)", content[:80], tweet_id)
    except Exception as exc:  # noqa: BLE001
        log.error("Tweet failed: %s", exc)
        db.execute("UPDATE posts SET status='failed' WHERE id=?", (post_id,))
    return post_id


def post_radar_posts(db: Any) -> int:
    """Post The Radar's 3 daily data tweets.

    Uses the latest drafted posts from The Brain, or generates template
    fallbacks from trend data if none exist.

    Args:
        db: Database instance.

    Returns:
        Number of posts published.
    """
    drafts = db.latest_posts(limit=5, platform="twitter", status="draft")
    if drafts:
        count = 0
        for post in drafts[:3]:
            post_tweet(db, post["content"], dry_run=True, post_type="radar")
            count += 1
        return count

    # No drafts — generate template posts from latest trends
    from .brain import fallback_social_posts
    trends = db.latest_trends(limit=10)
    posts = fallback_social_posts(trends)
    for p in posts:
        post_tweet(db, p, dry_run=True, post_type="radar")
    return len(posts)


# ---------------------------------------------------------------------------
# Replies & engagement
# ---------------------------------------------------------------------------

async def reply_to_mentions(db: Any, dry_run: bool = True) -> int:
    """Scan and reply to @mentions.

    In mock mode, uses seeded mock mentions so the pipeline is testable.
    In live mode, fetches recent mentions via the mentions timeline
    (requires elevated API tier) and replies.

    Args:
        db: Database instance.
        dry_run: If True, mock mode.

    Returns:
        Number of replies generated.
    """
    mentions: List[Dict[str, str]] = []

    if has_credentials() and not dry_run:
        try:
            client = make_client()
            me = client.get_me()
            user_id = me.data["id"]
            resp = client.get_users_mentions(
                id=user_id,
                max_results=20,
                tweet_fields="author_id,text,created_at",
                user_fields="username",
                expansions="author_id",
            )
            users = {u["id"]: u["username"] for u in (resp.includes or {}).get("users", [])}
            for tweet in resp.data or []:
                mentions.append({
                    "id": tweet["id"],
                    "author": users.get(tweet.get("author_id"), "anon"),
                    "text": tweet["text"],
                })
        except Exception as exc:  # noqa: BLE001
            log.warning("Mention scan failed: %s — using mock", exc)
            mentions = _mock_mentions()
    else:
        mentions = _mock_mentions()

    if not mentions:
        log.info("No new mentions to reply to")
        return 0

    from .brain import create_reply

    count = 0
    async with aiohttp.ClientSession() as session:
        for mention in mentions[:5]:
            # Prefer an AI-generated reply; fall back to a template on ANY failure
            try:
                reply_text = await create_reply(
                    db, session, mention["text"], mention["author"]
                )
            except Exception:  # noqa: BLE001
                reply_text = _template_reply(mention)

            # Register the reply in the DB
            reply_id = db.create_reply(
                reply_to=str(mention.get("id", mention["author"])),
                target_type="mention",
                content=reply_text,
                status="mock" if (dry_run or not has_credentials()) else "draft",
            )
            db.mark_reply_posted(reply_id, external_id=f"mock-reply-{reply_id}")
            log.info("Reply to @%s: %s", mention["author"], reply_text[:100])
            count += 1

    return count


def _template_reply(mention: Dict[str, str]) -> str:
    """Get a template reply (fallback when Brain API is not handy).

    Args:
        mention: Mention dict with author/text.

    Returns:
        ChadSatoshi-style reply string.
    """
    author = mention.get("author", "anon")
    return (
        f"Ayyy @{author}! 🤝 We're just out here analyzing the matrix 24/7. "
        "Keep grinding, anon! Not financial advice, just vibes. 🚀"
    )


def _mock_mentions() -> List[Dict[str, str]]:
    """Seed mock mentions for dry-run testing.

    Returns:
        List of mention dicts.
    """
    return [
        {"id": "mock1", "author": "cryptobro420", "text": "gm @OracleForgeBot what's trending today? 🚀"},
        {"id": "mock2", "author": "moonlambo", "text": "is @OracleForgeBot bullish on this memecoin? 👀"},
        {"id": "mock3", "author": "degendan", "text": "@OracleForgeBot your radar is goated fr 🔥"},
    ]


# ---------------------------------------------------------------------------
# Follow strategy
# ---------------------------------------------------------------------------

def follow_strategy(db: Any, dry_run: bool = True) -> int:
    """Follow up to TWITTER_DAILY_FOLLOW_LIMIT crypto accounts.

    In mock mode, simply logs the planned follow actions to the DB.
    In live mode, searches users by keywords and follows them.

    Args:
        db: Database instance.
        dry_run: If True, mock mode.

    Returns:
        Number of follows performed/planned.
    """
    limit = config.env_int("TWITTER_DAILY_FOLLOW_LIMIT", 50)
    keywords = config.env_list("TWITTER_FOLLOW_KEYWORDS", [
        "memecoin", "crypto", "defi", "altcoin", "web3", "solana",
    ])

    if dry_run or not has_credentials():
        log.info("Mock follow: would follow up to %d accounts matching %s",
                 limit, ", ".join(keywords[:3]))
        db.set_setting("last_follow_mock", f"{len(keywords)} keywords, limit {limit}")
        return len(keywords)  # simulated count

    try:
        client = make_client()
        me = client.get_me()
        my_id = me.data["id"]
        followed = 0
        for kw in keywords:
            if followed >= limit:
                break
            try:
                users = client.get_users(query=f"{kw} -is:verified_count:>1000",
                                         max_results=10).data or []
                for user in users[: (limit - followed)]:
                    if user.id != my_id:
                        client.follow_user(target_user_id=user.id)
                        followed += 1
                        log.info("Followed @%s (%s)", user.username, kw)
                        if followed >= limit:
                            break
            except Exception as exc:  # noqa: BLE001 — per-keyword isolation
                log.warning("Follow search '%s' failed: %s", kw, exc)
        db.set_setting("last_follow_count", str(followed))
        return followed
    except Exception as exc:  # noqa: BLE001
        log.error("Follow strategy failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Celebrity engagement
# ---------------------------------------------------------------------------

async def celebrity_engagement(db: Any, dry_run: bool = True) -> int:
    """Comment on unengaged celebrity posts in ChadSatoshi's voice.

    Args:
        db: Database instance.
        dry_run: If True, mock mode.

    Returns:
        Number of comments generated.
    """
    unengaged = db.unengaged_celebrity_posts(limit=10)
    if not unengaged:
        log.info("No unengaged celebrity posts")
        return 0

    from .brain import create_reply, load_prompt

    count = 0
    async with aiohttp.ClientSession() as session:
        for celeb in unengaged[:5]:
            load_prompt("celebrity_engagement").format(
                post_text=celeb["post_text"],
                celebrity_name=celeb["celebrity_name"],
                topic_hint=celeb.get("topic_hint", "event"),
            )
            try:
                reply_text = await create_reply(
                    db, session, celeb["post_text"], celeb["celebrity_name"]
                )
            except Exception:  # noqa: BLE001
                reply_text = (
                    f"Yo @{celeb['celebrity_name']} that {celeb.get('topic_hint', 'moment')} "
                    "was WILD! 🎉 Wish I could trade my HODL bags for a VIP pass. 🔥 #crypto #vibes"
                )

            reply_id = db.create_reply(
                reply_to=str(celeb["id"]),
                target_type="celebrity",
                content=reply_text,
                status="mock" if (dry_run or not has_credentials()) else "draft",
            )
            db.mark_reply_posted(reply_id, external_id=f"mock-celeb-{reply_id}")
            db.mark_celebrity_engaged(celeb["id"])
            log.info("Celebrity comment to @%s: %s", celeb["celebrity_name"], reply_text[:100])
            count += 1

    return count


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_twitter(mode: str = "radar_posts", db: Any = None, dry_run: bool = True) -> int:
    """Dispatch a Twitter behavior.

    Args:
        mode: radar_posts | replies | follow | celebrity_engagement.
        db: Optional Database instance.
        dry_run: If True, mock mode.

    Returns:
        Count of actions taken.
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    log.info("Twitter agent running (mode=%s, dry_run=%s)", mode, dry_run)

    if mode == "radar_posts":
        return post_radar_posts(db)
    if mode == "replies":
        return await reply_to_mentions(db, dry_run)
    if mode == "follow":
        return follow_strategy(db, dry_run)
    if mode == "celebrity_engagement":
        return await celebrity_engagement(db, dry_run)

    log.error("Unknown twitter mode: %s", mode)
    return 0
