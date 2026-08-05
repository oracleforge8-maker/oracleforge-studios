"""The Scout — OracleForge data scraping agents.

Async scrapers (aiohttp) that pull trending crypto/meme data from:

- Twitter/X        — trending hashtags, celebrity posts (event keywords), mentions
- Pump.fun         — new token launches, trending tokens
- CoinMarketCap    — top gainers, rankings (public web endpoint)
- DEXScreener      — trending pairs / new pairs
- Reddit           — r/CryptoCurrency, r/Memecoins hot posts

Design principles:
- Each source is an independent coroutine; a failure in one never blocks
  the others (per-source try/except isolation).
- All sources normalize to the same trend dict schema before storage.
- If a source lacks credentials or is unreachable, it falls back to
  ``mock`` data so the pipeline still exercises end-to-end (clearly
  flagged with ``source`` = e.g. "twitter_mock").
- Results are stored via the Chronicler DB and returned for wiring.

CLI:
    python main.py --run-scout [--sources twitter,pumpfun,cmc,reddit,dexscreener]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import aiohttp

from .. import config
from ..logger import get_logger
from ..utils import utcnow

log = get_logger("scout")

#: Max seconds to wait for any single HTTP call before giving up
HTTP_TIMEOUT = 15

#: Keywords used to detect celebrity "event" posts worth engaging with
CELEBRITY_EVENT_KEYWORDS = [
    "birthday", "party", "new album", "new car", "event", "celebration",
    "release", "launch", "dropped", "tour", "anniversary", "married",
    "wedding", "baby", "collab", "premiere",
]

#: Known celebrity handles seeded for demo/mock mode (extendable)
SEED_CELEBRITIES = [
    "elonmusk", "snoopdogg", "kanyewest", "mileycyrus", "therock",
    "sza", "chrisevans", "beyonce", "arianagrande", "cristiano",
]

#: Reddit subreddits to scan
REDDIT_SUBREDDITS = ["CryptoCurrency", "Memecoins", "SatoshiStreetBets"]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _trend(source: str, symbol: str, name: str = "", price: float = 0.0,
           change_pct: float = 0.0, volume: float = 0.0, mcap: float = 0.0,
           rank: int = 0, url: str = "", raw: Any = None) -> Dict[str, Any]:
    """Build a normalized trend dict.

    Args:
        source: Data source name (e.g. "pumpfun").
        symbol: Token symbol.
        name: Full token name.
        price: Current price in USD.
        change_pct: 24h price change percent.
        volume: 24h volume USD.
        mcap: Market cap USD.
        rank: Optional rank.
        url: Source URL.
        raw: Raw payload for archival.

    Returns:
        Normalized trend dict ready for ``db.insert_trend``.
    """
    return {
        "source": source,
        "token_symbol": (symbol or "").upper()[:32],
        "token_name": name or symbol,
        "price": float(price or 0),
        "price_change_pct": float(change_pct or 0),
        "volume_24h": float(volume or 0),
        "market_cap": float(mcap or 0),
        "rank": int(rank or 0),
        "url": url,
        "raw_data": json.dumps(raw, default=str) if raw is not None else None,
        "captured_at": utcnow(),
    }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _get_json(session: aiohttp.ClientSession, url: str,
                    headers: Optional[Dict[str, str]] = None,
                    params: Optional[Dict[str, str]] = None) -> Any:
    """Perform a GET and parse JSON with timeout + basic error handling.

    Args:
        session: aiohttp session.
        url: Target URL.
        headers: Optional request headers.
        params: Optional query params.

    Returns:
        Parsed JSON payload.

    Raises:
        aiohttp.ClientError / asyncio.TimeoutError on failure.
    """
    async with session.get(url, headers=headers, params=params,
                           timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


# ---------------------------------------------------------------------------
# Source scrapers
# ---------------------------------------------------------------------------

async def scrape_pumpfun(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch new/trending tokens from Pump.fun.

    Uses the public coin list endpoint (no auth required).
    Returns normalized trends.

    Args:
        session: aiohttp session.

    Returns:
        List of trend dicts (empty on failure).
    """
    trends: List[Dict[str, Any]] = []
    try:
        # Public endpoint: newest coins with 24h price change sorting
        url = "https://frontend-api.pump.fun/coins"
        params = {"limit": "20", "sort": "price_change_24h:desc", "order": "DESC"}
        data = await _get_json(session, url, params=params)
        rows = data if isinstance(data, list) else data.get("coins", [])
        for i, coin in enumerate(rows[:20], start=1):
            symbol = coin.get("symbol") or coin.get("ticker") or "?"
            name = coin.get("name") or symbol
            trends.append(_trend(
                source="pumpfun",
                symbol=symbol,
                name=name,
                price=coin.get("price_usd"),
                change_pct=coin.get("price_change_pct") or coin.get("price_change"),
                volume=coin.get("volume_24h") or coin.get("volume"),
                mcap=coin.get("market_cap"),
                rank=i,
                url=f"https://pump.fun/coin/{coin.get('mint', '')}" if coin.get("mint") else "",
                raw=coin,
            ))
        log.info("Pump.fun: %d tokens captured", len(trends))
    except Exception as exc:  # noqa: BLE001 — source isolation
        log.warning("Pump.fun scrape failed: %s", exc)
    return trends


async def scrape_cmc(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch top gainers from CoinMarketCap public web endpoint.

    Uses the anonymous trending/gainers API (no key required for
    the public listing JSON used by the website).

    Args:
        session: aiohttp session.

    Returns:
        List of trend dicts (empty on failure).
    """
    trends: List[Dict[str, Any]] = []
    try:
        url = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/spotlight"
        params = {
            "dataType": "1",     # 1 = gainers
            "limit": "20",
            "timeframe": "24h",
        }
        data = await _get_json(session, url, params=params)
        rows = data.get("data", {}).get("list", []) or []
        for i, coin in enumerate(rows[:20], start=1):
            quote = (coin.get("quotes") or [{}])[0]
            trends.append(_trend(
                source="cmc",
                symbol=coin.get("symbol", "?"),
                name=coin.get("name"),
                price=quote.get("price"),
                change_pct=quote.get("percentChange24h"),
                volume=quote.get("volume24h"),
                mcap=quote.get("marketCap"),
                rank=i,
                url=f"https://coinmarketcap.com/currencies/{coin.get('slug', '')}/",
                raw=coin,
            ))
        log.info("CMC: %d gainers captured", len(trends))
    except Exception as exc:  # noqa: BLE001
        log.warning("CMC scrape failed: %s", exc)
    return trends


async def scrape_dexscreener(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch trending/new pairs from DEXScreener public API.

    Args:
        session: aiohttp session.

    Returns:
        List of trend dicts (empty on failure).
    """
    trends: List[Dict[str, Any]] = []
    try:
        # New pairs (combo of boosts is paid; public new pairs endpoint is free)
        url = "https://api.dexscreener.com/token-profiles/latest/v1"
        data = await _get_json(session, url)
        rows = data if isinstance(data, list) else []
        for i, prof in enumerate(rows[:20], start=1):
            chain_id = prof.get("chainId", "?")
            addr = prof.get("tokenAddress", "")
            trends.append(_trend(
                source="dexscreener",
                symbol="?",
                name=prof.get("description", "").split(" ")[0] if prof.get("description") else "?",
                rank=i,
                url=f"https://dexscreener.com/{chain_id}/{addr}" if addr else "",
                raw=prof,
            ))
        log.info("DEXScreener: %d new pairs captured", len(trends))
    except Exception as exc:  # noqa: BLE001
        log.warning("DEXScreener scrape failed: %s", exc)
    return trends


async def scrape_reddit(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Fetch hot posts from crypto meme subreddits.

    Uses Reddit's public JSON endpoint (no auth needed for basic reads).

    Args:
        session: aiohttp session.

    Returns:
        List of trend dicts (empty on failure).
    """
    trends: List[Dict[str, Any]] = []
    try:
        for sub in REDDIT_SUBREDDITS:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json"
                headers = {"User-Agent": "OracleForgeScout/0.1 (research bot)"}
                data = await _get_json(session, url, headers=headers, params={"limit": "10"})
                children = data.get("data", {}).get("children", [])
                for i, child in enumerate(children[:8], start=1):
                    post = child.get("data", {})
                    title = post.get("title", "?")
                    # Crude extraction: if title mentions $SYMBOL, use it
                    symbol = "?"
                    for word in title.split():
                        if len(word) > 1 and word.startswith("$"):
                            symbol = word[1:].split()[0][:16]
                            break
                    trends.append(_trend(
                        source="reddit",
                        symbol=symbol,
                        name=sub,
                        rank=i,
                        url=f"https://www.reddit.com{post.get('permalink', '')}",
                        raw=post,
                    ))
            except Exception as exc:  # noqa: BLE001 — per-subreddit isolation
                log.warning("Reddit r/%s scrape failed: %s", sub, exc)
        log.info("Reddit: %d posts captured", len(trends))
    except Exception as exc:  # noqa: BLE001
        log.warning("Reddit scrape failed: %s", exc)
    return trends


async def scrape_twitter(session: aiohttp.ClientSession) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch Twitter trend/celebrity/mention data.

    Requires TWITTER_BEARER_TOKEN. If absent, returns mock data so the
    pipeline still demonstrates end-to-end behavior.

    Args:
        session: aiohttp session.

    Returns:
        Dict with keys: trends, celebrity_posts (normalized lists).
    """
    bearer = config.env("TWITTER_BEARER_TOKEN")
    if not bearer:
        log.info("Twitter: no bearer token — using mock data")
        return _mock_twitter_data()

    trends: List[Dict[str, Any]] = []
    celebrities: List[Dict[str, Any]] = []
    try:
        headers = {"Authorization": f"Bearer {bearer}"}

        # 1) Trending hashtags (available on free tier w/ bearer)
        try:
            url = "https://api.twitter.com/2/trends/by/woeid/23424977"  # US
            data = await _get_json(session, url, headers=headers)
            for item in data.get("data", [])[:15]:
                trends.append(_trend(
                    source="twitter",
                    symbol=item.get("name", "?").replace("#", "").upper(),
                    name=item.get("name"),
                    rank=item.get("rank", 0),
                    url="https://x.com/search?q=" + item.get("query", ""),
                    raw=item,
                ))
        except Exception as exc:  # noqa: BLE001
            log.warning("Twitter trends fetch failed: %s", exc)

        # 2) Celebrity posts via recent search (extended tier usually required;
        #    keep for when credentials permit)
        try:
            query = " OR ".join(f'"{kw}"' for kw in CELEBRITY_EVENT_KEYWORDS[:5])
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                "query": f"({query}) -is:retweet lang:en",
                "max_results": "20",
                "tweet.fields": "author_id,text,created_at",
                "expansions": "author_id",
                "user.fields": "username",
            }
            data = await _get_json(session, url, headers=headers, params=params)
            users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}
            for tweet in data.get("data", [])[:10]:
                handle = users.get(tweet.get("author_id"), "unknown")
                text = tweet.get("text", "")
                topic_hint = next(
                    (kw for kw in CELEBRITY_EVENT_KEYWORDS if kw.lower() in text.lower()), ""
                )
                celebrities.append({
                    "celebrity_name": handle,
                    "post_text": text,
                    "topic_hint": topic_hint,
                    "url": f"https://x.com/{handle}/status/{tweet.get('id', '')}",
                    "captured_at": utcnow(),
                })
        except Exception as exc:  # noqa: BLE001
            log.warning("Twitter celebrity fetch failed: %s", exc)

    except Exception as exc:  # noqa: BLE001
        log.warning("Twitter scrape failed: %s", exc)

    if not trends and not celebrities:
        log.info("Twitter: empty result — falling back to mock")
        return _mock_twitter_data()

    log.info("Twitter: %d trends, %d celebrity posts", len(trends), len(celebrities))
    return {"trends": trends, "celebrity_posts": celebrities}


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------

def _mock_twitter_data() -> Dict[str, List[Dict[str, Any]]]:
    """Generate branded mock Twitter data for demo/dry-run mode.

    Returns:
        Dict of mock trends and celebrity posts.
    """
    mock_trends = [
        _trend("twitter_mock", "DOGE", "Dogecoin", 0.321, 12.4, 1_200_000_000, 45_000_000_000, 1,
               "https://x.com/search?q=%23DOGE"),
        _trend("twitter_mock", "SHIB", "Shiba Inu", 0.000024, 9.1, 800_000_000, 14_000_000_000, 2,
               "https://x.com/search?q=%23SHIB"),
        _trend("twitter_mock", "PEPE", "Pepe", 0.000014, 34.2, 600_000_000, 5_900_000_000, 3,
               "https://x.com/search?q=%23PEPE"),
        _trend("twitter_mock", "BONK", "Bonk", 0.000028, 22.7, 300_000_000, 1_900_000_000, 4,
               "https://x.com/search?q=%23BONK"),
        _trend("twitter_mock", "WIF", "dogwifhat", 2.89, -4.3, 200_000_000, 2_900_000_000, 5,
               "https://x.com/search?q=%23WIF"),
        _trend("twitter_mock", "MOON", "MoonCoin", 0.0045, 145.0, 50_000_000, 45_000_000, 6,
               "https://x.com/search?q=%23MOON"),
    ]
    mock_celebs = [
        {
            "celebrity_name": "elonmusk",
            "post_text": "Just launched the new Tesla party mode! 🎉",
            "topic_hint": "party",
            "url": "https://x.com/elonmusk/status/mock1",
            "captured_at": utcnow(),
        },
        {
            "celebrity_name": "snoopdogg",
            "post_text": "It's my birthday month! Celebration time 🎂🔥",
            "topic_hint": "birthday",
            "url": "https://x.com/snoopdogg/status/mock2",
            "captured_at": utcnow(),
        },
    ]
    return {"trends": mock_trends, "celebrity_posts": mock_celebs}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_scout(sources: str = "", session: Optional[aiohttp.ClientSession] = None,
                    db: Any = None) -> Dict[str, int]:
    """Run all enabled scout scrapers and store normalized results.

    Args:
        sources: Comma-separated source filter (empty = all). Valid values:
                 twitter, pumpfun, cmc, dexscreener, reddit.
        session: Optional shared aiohttp session (created if None).
        db: Optional Database instance (defaults to module singleton).

    Returns:
        Dict summary: {"trends": int, "celebrity_posts": int}.
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    enabled = {s.strip() for s in sources.split(",") if s.strip()} or {
        "twitter", "pumpfun", "cmc", "dexscreener", "reddit",
    }

    log.info("Scout starting. Sources: %s", ", ".join(sorted(enabled)))

    async with session or aiohttp.ClientSession() as own_session:  # type: ignore[union-attr]
        s = own_session

        # Launch all enabled source scrapers concurrently
        tasks: Dict[str, asyncio.Task] = {}
        if "twitter" in enabled:
            tasks["twitter"] = asyncio.create_task(scrape_twitter(s))
        if "pumpfun" in enabled:
            tasks["pumpfun"] = asyncio.create_task(scrape_pumpfun(s))
        if "cmc" in enabled:
            tasks["cmc"] = asyncio.create_task(scrape_cmc(s))
        if "dexscreener" in enabled:
            tasks["dexscreener"] = asyncio.create_task(scrape_dexscreener(s))
        if "reddit" in enabled:
            tasks["reddit"] = asyncio.create_task(scrape_reddit(s))

        trend_count = 0
        celeb_count = 0

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for name, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    log.warning("%s source crashed: %s", name, result)
                    continue

                # Twitter returns a dict of trends + celebrity_posts
                if name == "twitter":
                    twitter_data = result
                    for t in twitter_data.get("trends", []):
                        db.insert_trend(t)
                        trend_count += 1
                    for celeb in twitter_data.get("celebrity_posts", []):
                        db.insert_celebrity_post(
                            celebrity_name=celeb["celebrity_name"],
                            post_text=celeb["post_text"],
                            topic_hint=celeb.get("topic_hint", ""),
                            url=celeb.get("url", ""),
                        )
                        celeb_count += 1
                    continue

                # All other sources return a plain list of trend dicts
                for t in result or []:
                    db.insert_trend(t)
                    trend_count += 1

    log.info("Scout complete: %d trends, %d celebrity posts stored", trend_count, celeb_count)
    return {"trends": trend_count, "celebrity_posts": celeb_count}
