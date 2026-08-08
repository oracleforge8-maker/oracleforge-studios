"""OracleForge Flask web server.

Serves the multi-page marketing site and JSON APIs:

Pages:
    /            Home (hero + live trend widget + waitlist CTA)
    /tools       Product cards (Radar / Radar Pro / Forge)
    /live-demo   Live Scout feed
    /pricing     Tier comparison + referral + free trial
    /blog        The Degen Dispatch (latest 5 posts)
    /about       Cult of the Machine narrative
    /waitlist    Email capture + referral program

APIs:
    GET  /api/trends?limit=N     Latest trends (for live widgets)
    GET  /api/ticker             Homepage market ticker (BTC/ETH/SOL + gainers)
    GET  /api/top-gainers        Top 10 coins by 30m momentum
    GET  /api/pump-trending      Trending Pump.fun meme coins (Three.ws)
    POST /api/waitlist           Add subscriber (email, name, referred_by)
    POST /api/newsletter         Subscribe to newsletter (email)

Run:
    python main.py --serve-web [--port 5000]
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from src import config
from src.logger import get_logger

log = get_logger("web")

#: Flask app instance (imported by main.py)
app = Flask(__name__)
app.secret_key = config.env("FLASK_SECRET_KEY", "dev-secret")
CORS(app)

#: Simple email validation regex
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db() -> Any:
    """Return the shared database instance.

    Returns:
        Database instance.
    """
    from src.database import get_db
    return get_db()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Render the home page."""
    return render_template("home.html")


@app.route("/tools")
def tools():
    """Render the tools page."""
    return render_template("tools.html")


@app.route("/live-demo")
def live_demo():
    """Render the live demo page."""
    return render_template("live_demo.html")


@app.route("/pricing")
def pricing():
    """Render the pricing page."""
    return render_template("pricing.html")


@app.route("/blog")
def blog():
    """Render the blog page with the latest 5 posts."""
    db = _db()
    posts = db.latest_posts(limit=10)
    # Add a derived title for display
    for p in posts:
        p["title"] = _post_title(p)
    return render_template("blog.html", posts=posts)


@app.route("/about")
def about():
    """Render the about page."""
    return render_template("about.html")


@app.route("/waitlist")
def waitlist():
    """Render the waitlist page."""
    return render_template("waitlist.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Chart data (CoinGecko /coins/{id}/ohlc)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/chart/<coin>):
#     {
#         "coin": "PEPE",
#         "price_data": [[timestamp, open, high, low, close, volume]],
#         "ma_3h": [],
#         "ma_10h": [],
#         "signals": [
#             {"time": timestamp, "type": "entry" | "exit", "price": 0}
#         ]
#     }
#
# Live data is pulled from CoinGecko. When COINGECKO_API_KEY is unset (or the
# API is unreachable) we fall back to branded mock data so the chart always
# renders — the same graceful-degradation pattern used by the ticker.
# Refreshed by the frontend as needed.

#: CoinGecko API v3 base URL
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

#: Per-request hard timeout (seconds) so a slow CG can never stall the page
_COINGECKO_TIMEOUT = 10


def _coingecko_headers() -> Dict[str, str]:
    """Build request headers for a CoinGecko call.

    Injects the configured API key (if any). CoinGecko accepts the key via the
    ``x-cg-pro-api-key`` header (paid plans) or ``x-cg-demo-api-key`` (free/demo)
    — we send the pro header; demo keys generally work here too. The request
    is best-effort: the endpoint degrades to mock data on any failure.

    Returns:
        Headers dict, including the API key header when configured.
    """
    headers: Dict[str, str] = {"accept": "application/json"}
    key = config.env("COINGECKO_API_KEY")
    if key:
        headers["x-cg-pro-api-key"] = key
    return headers


def _coingecko_chart_data(coin_id: str, timeframe: str = "1m") -> Dict[str, Any]:
    """Fetch OHLC data from CoinGecko and calculate moving averages.

    Args:
        coin_id: CoinGecko coin ID (e.g., "pepe", "bitcoin").
        timeframe: Timeframe for the chart (default "1m").

    Returns:
        Dict with price_data, ma_1m, ma_5m, and signals.
    """
    # Map timeframe to CoinGecko days parameter
    days_map = {
        "1m": 0.05,  # 1 hour for 1m chart (720 minutes / 1440 minutes per day)
        "5m": 0.25,  # 6 hours for 5m chart
        "15m": 0.5,  # 12 hours for 15m chart
        "1h": 1,     # 1 day for 1h chart
        "4h": 2,     # 2 days for 4h chart
        "1d": 7,     # 7 days for daily chart
    }
    days = days_map.get(timeframe, 0.05)

    try:
        # Fetch OHLC data from CoinGecko
        resp = requests.get(
            f"{COINGECKO_BASE}/coins/{coin_id}/ohlc",
            params={
                "vs_currency": "usd",
                "days": days
            },
            headers=_coingecko_headers(),
            timeout=_COINGECKO_TIMEOUT,
        )
        resp.raise_for_status()
        ohlc_data = resp.json()

        # Process data and calculate moving averages
        price_data = []
        closes = []

        for candle in ohlc_data:
            timestamp = candle[0]
            open_price = candle[1]
            high = candle[2]
            low = candle[3]
            close = candle[4]
            volume = candle[5] if len(candle) > 5 else 0

            price_data.append([timestamp, open_price, high, low, close, volume])
            closes.append(close)

        # Calculate moving averages based on timeframe
        ma_1m = []
        ma_5m = []

        # Determine MA periods based on timeframe
        ma_1_period = 1  # 1-minute MA
        ma_5_period = 5  # 5-minute MA

        for i in range(len(closes)):
            if i >= ma_1_period:
                ma_1m.append(sum(closes[i-ma_1_period:i+1]) / (ma_1_period + 1))  # 1-period MA
            else:
                ma_1m.append(None)

            if i >= ma_5_period:
                ma_5m.append(sum(closes[i-ma_5_period:i+1]) / (ma_5_period + 1))  # 5-period MA
            else:
                ma_5m.append(None)

        # Generate simple signals (for demo purposes)
        signals = []
        for i in range(1, len(closes)):
            if i >= ma_5_period and ma_1m[i] and ma_5m[i]:
                if ma_1m[i] > ma_5m[i] and (i == 1 or ma_1m[i-1] <= ma_5m[i-1]):
                    signals.append({
                        "time": price_data[i][0],
                        "type": "entry",
                        "price": closes[i]
                    })
                elif ma_1m[i] < ma_5m[i] and (i == 1 or ma_1m[i-1] >= ma_5m[i-1]):
                    signals.append({
                        "time": price_data[i][0],
                        "type": "exit",
                        "price": closes[i]
                    })

        return {
            "coin": coin_id.upper(),
            "price_data": price_data,
            "ma_1m": ma_1m,
            "ma_5m": ma_5m,
            "signals": signals
        }

    except Exception as exc:
        log.warning("Chart data fetch failed for %s: %s", coin_id, exc)
        return {
            "coin": coin_id.upper(),
            "price_data": [],
            "ma_1m": [],
            "ma_5m": [],
            "signals": []
        }


def _mock_chart_data(coin_id: str) -> Dict[str, Any]:
    """Branded fallback chart data (used without a key or on API failure).

    Returns sample data so the chart always renders something meaningful.
    """
    # Generate mock OHLC data for the last 24 hours (3h intervals = 8 candles)
    now = int(time.time() * 1000)
    price_data = []
    base_price = 0.0000142  # PEPE-like price

    for i in range(8):
        timestamp = now - (8 - i) * 3 * 60 * 60 * 1000  # 3h intervals
        price = base_price * (1 + (i * 0.05 - 0.15))  # Some variation
        price_data.append([
            timestamp,
            price * 0.98,  # open
            price * 1.02,  # high
            price * 0.95,  # low
            price,         # close
            1000000        # volume
        ])

    # Calculate mock moving averages
    closes = [candle[4] for candle in price_data]
    ma_1m = [sum(closes[max(0, i-1):i+1]) / min(2, i+1) for i in range(len(closes))]
    ma_5m = [sum(closes[max(0, i-5):i+1]) / min(6, i+1) for i in range(len(closes))]

    # Generate mock signals
    signals = []
    if len(price_data) > 2:
        signals.append({
            "time": price_data[2][0],
            "type": "entry",
            "price": price_data[2][4]
        })
        signals.append({
            "time": price_data[5][0],
            "type": "exit",
            "price": price_data[5][4]
        })

    return {
        "coin": coin_id.upper(),
        "price_data": price_data,
        "ma_1m": ma_1m,
        "ma_5m": ma_5m,
        "signals": signals
    }


@app.route('/api/chart/<symbol>')
def chart(symbol):
    import requests
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": 1,
            "interval": "5m"
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        prices = data.get('prices', [])
        volumes = data.get('total_volumes', [])
        
        price_data = []
        for i, p in enumerate(prices):
            price_data.append([p[0], p[1], p[1], p[1], p[1], volumes[i][1] if i < len(volumes) else 0])
        
        return jsonify({
            "price_data": price_data,
            "ma_1m": [],
            "ma_5m": [],
            "signals": []
        })
    except Exception as e:
        return jsonify(_mock_chart_data(symbol))


# ---------------------------------------------------------------------------
# Quick Stats (CoinGecko /global)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/quick-stats):
#     {
#         "total_market_cap": 2500000000000,
#         "total_volume": 85000000000,
#         "btc_dominance": 52.5,
#         "eth_dominance": 18.2
#     }
#
# Live data is pulled from CoinGecko /global endpoint. When COINGECKO_API_KEY
# is unset (or the API is unreachable) we fall back to branded mock data so the
# stats always render — the same graceful-degradation pattern used by the ticker.
# Refreshed by the frontend every 60 seconds.

def _coingecko_global_data() -> Dict[str, Any]:
    """Fetch global market data from CoinGecko /global endpoint.
    Returns:
        Dict with total_market_cap, total_volume, btc_dominance, eth_dominance.
    """
    resp = requests.get(
        f"{COINGECKO_BASE}/global",
        headers=_coingecko_headers(),
        timeout=_COINGECKO_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {}) or {}

    out: Dict[str, Any] = {}
    market_cap_usd = data.get("total_market_cap", {}).get("usd")
    if market_cap_usd is not None:
        out["total_market_cap"] = float(market_cap_usd)

    total_volume_usd = data.get("total_volume", {}).get("usd")
    if total_volume_usd is not None:
        out["total_volume"] = float(total_volume_usd)

    btc_dominance = data.get("market_cap_percentage", {}).get("btc")
    if btc_dominance is not None:
        out["btc_dominance"] = float(btc_dominance)

    eth_dominance = data.get("market_cap_percentage", {}).get("eth")
    if eth_dominance is not None:
        out["eth_dominance"] = float(eth_dominance)

    return out


def _mock_quick_stats_data() -> Dict[str, Any]:
    """Branded fallback quick stats payload (used without a key or on API failure).
    Returns sample data so the stats always render something meaningful.
    Returns:
        Dict matching the public /api/quick-stats schema.
    """
    return {
        "total_market_cap": 2500000000000,
        "total_volume": 85000000000,
        "btc_dominance": 52.5,
        "eth_dominance": 18.2
    }


@app.route('/api/quick-stats')
def quick_stats():
    import requests
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=10)
        data = response.json()
        global_data = data.get('data', {})
        return jsonify({
            "total_market_cap": global_data.get('total_market_cap', {}).get('usd', 0),
            "total_volume": global_data.get('total_volume', {}).get('usd', 0),
            "btc_dominance": global_data.get('market_cap_percentage', {}).get('btc', 0),
            "eth_dominance": global_data.get('market_cap_percentage', {}).get('eth', 0)
        })
    except Exception as e:
        return jsonify({
            "total_market_cap": 2140000000000,
            "total_volume": 85300000000,
            "btc_dominance": 52.5,
            "eth_dominance": 18.2
        })


# ---------------------------------------------------------------------------
# Breaking News ticker (CryptoPanic)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/news):
#     {
#         "news": [
#             {"title": "Bitcoin Surges Past $65K...", "url": "https://...", "source": "CoinDesk"},
#             {"title": "Ethereum ETFs Approved...", "url": "https://...", "source": "CoinTelegraph"},
#             ...
#         ]
#     }
#
# Live data is pulled from CryptoPanic API when CRYPTOPANIC_API_KEY is configured.
# When no key is set (or the API is unreachable) we fall back to branded mock
# data so the ticker always renders — the same graceful-degradation pattern
# used by other tickers. Refreshed by the frontend every 5 minutes.

#: CryptoPanic API v1 base URL
CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1"

#: Per-request hard timeout (seconds) so a slow CryptoPanic can never stall the page
_CRYPTOPANIC_TIMEOUT = 10


def _cryptopanic_headers() -> Dict[str, str]:
    """Build request headers for a CryptoPanic call.
    Returns:
        Headers dict, including the API key header when configured.
    """
    headers: Dict[str, str] = {"accept": "application/json"}
    key = config.env("CRYPTOPANIC_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _cryptopanic_latest_news() -> List[Dict[str, Any]]:
    """Fetch latest crypto news from CryptoPanic /posts/ endpoint.
    Returns:
        List of dicts: {"title", "url", "source"}.
    """
    resp = requests.get(
        f"{CRYPTOPANIC_BASE}/posts/",
        params={
            "public": "true",
            "filter": "hot",
            "regions": "en",
            "kind": "news",
            "limit": 10
        },
        headers=_cryptopanic_headers(),
        timeout=_CRYPTOPANIC_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    results: List[Dict[str, Any]] = data.get("results", [])

    out: List[Dict[str, Any]] = []
    for post in results:
        out.append({
            "title": post.get("title", "Breaking Crypto News"),
            "url": post.get("url", ""),
            "source": post.get("domain", "Source")
        })
    return out


def _mock_news_data() -> List[Dict[str, Any]]:
    """Branded fallback news data (used without a key or on API failure).
    Returns sample headlines so the ticker always renders something meaningful.
    Returns:
        List of dicts: {"title", "url", "source"}.
    """
    return [
        {"title": "Bitcoin Surges Past $65K as Institutional Adoption Accelerates", "url": "https://example.com/bitcoin-surge", "source": "CoinDesk"},
        {"title": "Ethereum ETFs Approved by SEC, ETH Price Jumps 12%", "url": "https://example.com/eth-etf", "source": "CoinTelegraph"},
        {"title": "Solana Network Outage Resolved After 5-Hour Downtime", "url": "https://example.com/solana-outage", "source": "The Block"},
        {"title": "MicroStrategy Adds 12,000 More BTC to Treasury, Now Holds 226,331 Bitcoin", "url": "https://example.com/microstrategy-btc", "source": "Decrypt"},
        {"title": "SEC Delays Decision on Spot Bitcoin ETFs Until October", "url": "https://example.com/sec-delay", "source": "Bloomberg"},
        {"title": "Vitalik Buterin Proposes New EIP to Reduce Ethereum Gas Fees by 30%", "url": "https://example.com/vitalik-eip", "source": "CryptoBriefing"},
        {"title": "Binance Launches New DeFi Staking Platform with 20% APY", "url": "https://example.com/binance-defi", "source": "CoinDesk"},
        {"title": "Cardano Vasil Hard Fork Successfully Completed, ADA Price Rallies", "url": "https://example.com/cardano-vasil", "source": "CoinTelegraph"}
    ]


@app.route("/api/news")
def api_news():
    """Latest crypto news headlines for the breaking news ticker.
    Uses live CryptoPanic data when CRYPTOPANIC_API_KEY is configured;
    otherwise (and on any API failure) returns branded mock data so the
    ticker always displays. Refreshed by the frontend every 5 minutes.
    Returns:
        JSON: {"news": [{"title", "url", "source"}, ...]}
    """
    if not config.env("CRYPTOPANIC_API_KEY"):
        log.info("News: no CRYPTOPANIC_API_KEY configured — serving mock data")
        return jsonify({"news": _mock_news_data()})

    try:
        news_items = _cryptopanic_latest_news()
        return jsonify({"news": news_items})
    except Exception as exc:  # noqa: BLE001 — never break the homepage
        log.warning("News: CryptoPanic fetch failed (%s) — serving mock data", exc)
        return jsonify({"news": _mock_news_data()})


@app.route("/api/trends")
def api_trends():
    """Return the latest trends as JSON.

    Query params:
        limit: Max rows (default 20).

    Returns:
        JSON: {"trends": [...]}
    """
    try:
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 20

    db = _db()
    trends = db.latest_trends(limit=limit)
    return jsonify({"trends": trends})


# ---------------------------------------------------------------------------
# Homepage market ticker (CoinGecko)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/ticker):
#     {
#         "btc": {"price": 0, "change_24h": 0},
#         "eth": {"price": 0, "change_24h": 0},
#         "sol": {"price": 0, "change_24h": 0},
#         "top_gainers": [
#             {"rank": 1, "symbol": "PEPE", "price": 0, "change_30m": 0},
#             {"rank": 2, "symbol": "DOGE", "price": 0, "change_30m": 0},
#             {"rank": 3, "symbol": "SHIB", "price": 0, "change_30m": 0},
#         ]
#     }
#
# Live data is pulled from CoinGecko. When COINGECKO_API_KEY is unset (or the
# API is unreachable) we fall back to branded mock data so the ticker always
# renders — the same graceful-degradation pattern used by the Scout.

#: CoinGecko coin IDs for the major pairs the ticker highlights
_TICKER_COINS = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
}

#: Number of top gainers surfaced by the ticker
_TICKER_GAINERS_LIMIT = 3

#: Number of top gainers surfaced by the dedicated /api/top-gainers table
_GAINERS_LIMIT = 10


def _coingecko_simple_prices() -> Dict[str, Dict[str, float]]:
    """Fetch BTC/ETH/SOL prices + 24h change from CoinGecko /simple/price.

    Returns:
        Dict keyed by ticker symbol ("btc"/"eth"/"sol") with *price* and
        *change_24h* keys.
    """
    resp = requests.get(
        f"{COINGECKO_BASE}/simple/price",
        params={
            "ids": ",".join(_TICKER_COINS.values()),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        },
        headers=_coingecko_headers(),
        timeout=_COINGECKO_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    out: Dict[str, Dict[str, float]] = {}
    for symbol, coin_id in _TICKER_COINS.items():
        entry = data.get(coin_id, {}) or {}
        out[symbol] = {
            "price": float(entry.get("usd", 0) or 0),
            "change_24h": float(entry.get("usd_24h_change", 0) or 0),
        }
    return out


def _coingecko_top_gainers() -> List[Dict[str, Any]]:
    """Fetch the top gainers ranked by the finest available momentum (1h).

    CoinGecko's public API does not expose a 30m price change, so we rank by
    the 1h change (``price_change_percentage_1h_in_currency``) — the finest
    timeframe available without a paid endpoint — and surface it under the
    ``change_30m`` key in the ticker payload. The mock fallback supplies
    genuine 30m-style figures for demo mode.

    We sort client-side because the ``order`` query param is not reliably
    honoured by the demo endpoint.

    Returns:
        List of dicts: {"rank", "symbol", "price", "change_30m"}.
    """
    resp = requests.get(
        f"{COINGECKO_BASE}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "price_change_percentage": "1h",
        },
        headers=_coingecko_headers(),
        timeout=_COINGECKO_TIMEOUT,
    )
    resp.raise_for_status()
    coins: List[Dict[str, Any]] = resp.json()

    def _change_1h(coin: Dict[str, Any]) -> float:
        val = coin.get("price_change_percentage_1h_in_currency")
        if isinstance(val, list):
            val = val[0] if val else 0
        if val is None:
            val = coin.get("price_change_percentage_1h", 0)
        try:
            return float(val or 0)
        except (TypeError, ValueError):
            return 0.0

    ranked = sorted(coins, key=_change_1h, reverse=True)[:_TICKER_GAINERS_LIMIT]

    out: List[Dict[str, Any]] = []
    for rank, coin in enumerate(ranked, start=1):
        out.append({
            "rank": rank,
            "symbol": (coin.get("symbol") or "?").upper(),
            "price": float(coin.get("current_price", 0) or 0),
            "change_30m": _change_1h(coin),
        })
    return out


def _coingecko_ticker_data() -> Dict[str, Any]:
    """Assemble the full ticker payload from CoinGecko (live).

    Returns:
        Dict matching the public /api/ticker schema.
    """
    prices = _coingecko_simple_prices()
    gainers = _coingecko_top_gainers()
    result: Dict[str, Any] = dict(prices)
    result["top_gainers"] = gainers
    return result


def _mock_ticker_data() -> Dict[str, Any]:
    """Branded fallback ticker payload (used without a key or on API failure).

    Returns:
        Dict matching the public /api/ticker schema with sample data so the
        ticker always renders something meaningful.
    """
    return {
        "btc": {"price": 64728.14, "change_24h": 0.76},
        "eth": {"price": 1908.32, "change_24h": -0.27},
        "sol": {"price": 73.44, "change_24h": 0.05},
        "top_gainers": [
            {"rank": 1, "symbol": "PEPE", "price": 0.0000142, "change_30m": 12.4},
            {"rank": 2, "symbol": "BOME", "price": 0.0004210, "change_30m": 8.9},
            {"rank": 3, "symbol": "WIF", "price": 2.8941, "change_30m": 6.3},
        ],
    }


@app.route('/api/ticker')
def ticker():
    import requests
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum,solana",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return jsonify({
            "btc": {
                "price": data.get("bitcoin", {}).get("usd", 0),
                "change_24h": data.get("bitcoin", {}).get("usd_24h_change", 0)
            },
            "eth": {
                "price": data.get("ethereum", {}).get("usd", 0),
                "change_24h": data.get("ethereum", {}).get("usd_24h_change", 0)
            },
            "sol": {
                "price": data.get("solana", {}).get("usd", 0),
                "change_24h": data.get("solana", {}).get("usd_24h_change", 0)
            },
            "top_gainers": []
        })
    except Exception as e:
        return jsonify({
            "btc": {"price": 61234, "change_24h": 2.4},
            "eth": {"price": 2912, "change_24h": 12.4},
            "sol": {"price": 143, "change_24h": 0.8},
            "top_gainers": []
        })


# ---------------------------------------------------------------------------
# Top 10 Gainers table (CoinGecko /coins/markets)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/top-gainers): a JSON array of 10 coins:
#     [
#         {"rank": 1, "symbol": "PEPE", "price": 0.0000142,
#          "change_30m": 14.5, "change_24h": 3.2},
#         ...
#     ]
#
# CoinGecko's public /coins/markets endpoint does not expose a 30-minute
# price change, so we rank by the finest available momentum
# (``price_change_percentage_1h_in_currency``, 1h) — the same proxy used by
# the ticker — and surface it under ``change_30m``. The 24h change is also
# requested and returned as ``change_24h``. The mock fallback supplies
# branded sample rows so the table always renders. Refreshed by the frontend
# every 60 seconds.


def _change_pct(coin: Dict[str, Any], field: str) -> float:
    """Extract a percentage figure from a CoinGecko coin dict.

    CoinGecko returns ``price_change_percentage_<range>_in_currency`` as a
    single-element list (or a bare float); this helper normalises both forms.

    Args:
        coin: A single /coins/markets response object.
        field: The CoinGecko field name, e.g.
            ``price_change_percentage_1h_in_currency``.

    Returns:
        The percentage as a float (0.0 on any parse failure).
    """
    val = coin.get(field)
    if isinstance(val, list):
        val = val[0] if val else 0
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _coingecko_top_gainers_table(count: int = _GAINERS_LIMIT) -> List[Dict[str, Any]]:
    """Fetch the top gainers ranked by the finest available momentum (1h).

    Queries ``/coins/markets`` (sorted client-side by
    ``price_change_percentage_1h_in_currency`` descending, per the data
    source spec) and returns a compact payload including both the 30m
    momentum (1h proxy) and the 24h change.

    Args:
        count: How many ranks to return (default 10).

    Returns:
        List of dicts: {"rank", "symbol", "price", "change_30m", "change_24h"}.
    """
    resp = requests.get(
        f"{COINGECKO_BASE}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "price_change_percentage": "1h,24h",
        },
        headers=_coingecko_headers(),
        timeout=_COINGECKO_TIMEOUT,
    )
    resp.raise_for_status()
    coins: List[Dict[str, Any]] = resp.json()

    ranked = sorted(
        coins,
        key=lambda c: _change_pct(c, "price_change_percentage_1h_in_currency"),
        reverse=True,
    )[:count]

    out: List[Dict[str, Any]] = []
    for rank, coin in enumerate(ranked, start=1):
        out.append({
            "rank": rank,
            "symbol": (coin.get("symbol") or "?").upper(),
            "price": float(coin.get("current_price", 0) or 0),
            "change_30m": _change_pct(coin, "price_change_percentage_1h_in_currency"),
            "change_24h": _change_pct(coin, "price_change_percentage_24h_in_currency"),
        })
    return out


def _mock_gainers_data(count: int = _GAINERS_LIMIT) -> List[Dict[str, Any]]:
    """Branded fallback for the top-gainers table (used without a key or on API failure).

    Returns sample rows (with both 30m and 24h changes) so the table always
    renders something meaningful and visually consistent with the live schema.

    Args:
        count: How many mock rows to return.

    Returns:
        List of dicts: {"rank", "symbol", "price", "change_30m", "change_24h"}.
    """
    sample = [
        {"symbol": "PEPE", "price": 0.0000142, "change_30m": 14.5, "change_24h": 3.2},
        {"symbol": "BOME", "price": 0.0004210, "change_30m": 8.9, "change_24h": 1.8},
        {"symbol": "WIF", "price": 2.8941, "change_30m": 6.3, "change_24h": -2.1},
        {"symbol": "DOGE", "price": 0.0734, "change_30m": 5.7, "change_24h": 4.5},
        {"symbol": "SHIB", "price": 0.0000131, "change_30m": 4.9, "change_24h": 2.3},
        {"symbol": "FLOKI", "price": 0.0001872, "change_30m": 4.2, "change_24h": 1.1},
        {"symbol": "INJ", "price": 14.27, "change_30m": 3.8, "change_24h": -1.5},
        {"symbol": "OP", "price": 1.99, "change_30m": 3.4, "change_24h": 5.0},
        {"symbol": "PYTH", "price": 0.312, "change_30m": 3.1, "change_24h": 2.8},
        {"symbol": "ARB", "price": 3.47, "change_30m": 2.9, "change_24h": 6.7},
    ]
    out: List[Dict[str, Any]] = []
    for rank, coin in enumerate(sample[:count], start=1):
        out.append({
            "rank": rank,
            "symbol": coin["symbol"],
            "price": coin["price"],
            "change_30m": coin["change_30m"],
            "change_24h": coin["change_24h"],
        })
    return out


@app.route("/api/top-gainers")
def api_top_gainers():
    """Top 10 coins by 30-minute price momentum.

    Uses live CoinGecko data when ``COINGECKO_API_KEY`` is configured;
    otherwise (and on any API failure) returns branded mock data so the
    table always displays. Refreshed by the frontend every 60 seconds.

    Returns:
        JSON: a 10-element array of
        {"rank", "symbol", "price", "change_30m", "change_24h"}.
    """
    if not config.env("COINGECKO_API_KEY"):
        log.info("Top gainers: no COINGECKO_API_KEY configured — serving mock data")
        return jsonify(_mock_gainers_data())

    try:
        return jsonify(_coingecko_top_gainers_table())
    except Exception as exc:  # noqa: BLE001 — never break the homepage
        log.warning("Top gainers: CoinGecko fetch failed (%s) — serving mock data", exc)
        return jsonify(_mock_gainers_data())


# ---------------------------------------------------------------------------
# Pump.fun Trending (Three.ws)
# ---------------------------------------------------------------------------
# Public schema (returned by /api/pump-trending):
#     {
#         "tokens": [
#             {"symbol": "TROLL", "name": "TROLL", "price": 0.0374,
#              "momentum": 80.6, "launched": "5 min ago",
#              "marketCapUsd": 37389476.99, "volumeUsd": 12984.03,
#              "url": "https://pump.fun/coin/..."},
#         ],
#         "window": "1h",
#         "ts": "2026-08-07T17:50:45.805Z",
#         "sources": ["pumpfun", "dexscreener"],
#         "note": "...",
#         "count": 1
#     }
#
# Live data is pulled from the free Three.ws API (no key required). On any
# upstream failure we fall back to branded mock data so the section always
# renders — the same graceful-degradation pattern used by the ticker.
# Refreshed by the frontend every 60 seconds.

#: Three.ws API base URL (free, no API key)
THREEWS_BASE = "https://three.ws/api"

#: Per-request hard timeout (seconds) so a slow upstream never stalls the page
_THREEWS_TIMEOUT = 10

#: Assumed token supply for deriving a synthetic per-token price from market cap.
# Pump.fun meme coins typically float ~1 B tokens; we use this to convert
# marketCapUsd → a notional price (since the Three.ws API does not expose a
# per-token price directly).
_PUMP_SUPPLY = 1_000_000_000


def _time_since(ts_str: str) -> str:
    """Format an ISO-8601 timestamp as a short relative duration.

    Args:
        ts_str: ISO-8601 timestamp (e.g. Three.ws ``ts`` field).

    Returns:
        Short label like "12 min ago", "3h ago", "1d ago", or "Recently".
    """
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        secs = max(0, (now - ts).total_seconds())
        if secs < 60:
            return f"{int(secs)}s ago"
        if secs < 3600:
            return f"{int(secs / 60)} min ago"
        if secs < 86400:
            return f"{int(secs / 3600)}h ago"
        return f"{int(secs / 86400)}d ago"
    except (ValueError, TypeError, AttributeError):
        return "Recently"


def _threews_pump_tokens() -> Dict[str, Any]:
    """Fetch trending Pump.fun tokens from Three.ws and normalize them.

    The Three.ws API returns raw token data with a ``score`` (0-100 momentum)
    and ``marketCapUsd``. We normalize each token into the schema above:

    - ``momentum`` ← ``score`` (clamped to 0–100)
    - ``price`` ← ``marketCapUsd / _PUMP_SUPPLY`` (synthetic per-token price)
    - ``launched`` ← relative time since the data timestamp ``ts``

    Returns:
        Normalized payload dict matching the /api/pump-trending schema.
    """
    resp = requests.get(
        f"{THREEWS_BASE}/crypto/trending",
        params={"window": "1h", "source": "pump.fun"},
        headers={"accept": "application/json"},
        timeout=_THREEWS_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json()

    tokens: List[Dict[str, Any]] = []
    for t in raw.get("tokens", []):
        mc = float(t.get("marketCapUsd", 0) or 0)
        score = float(t.get("score", 0) or 0)
        tokens.append({
            "symbol": (t.get("symbol") or "???").upper(),
            "name": t.get("name") or "",
            "price": round(mc / _PUMP_SUPPLY, 8),
            "momentum": round(max(0.0, min(100.0, score)), 1),
            "launched": _time_since(raw.get("ts", "")),
            "marketCapUsd": round(mc, 2),
            "volumeUsd": round(float(t.get("volumeUsd", 0) or 0), 2),
            "url": t.get("url") or "",
        })

    return {
        "tokens": tokens,
        "window": raw.get("window", "1h"),
        "ts": raw.get("ts", ""),
        "sources": raw.get("sources", []),
        "note": raw.get("note", ""),
        "count": len(tokens),
    }


def _mock_pump_tokens() -> Dict[str, Any]:
    """Branded fallback for the Pump.fun trending section.

    Returns sample tokens with all schema fields so the section always
    renders something meaningful and visually consistent with the live schema.
    Two tokens have momentum > 70 to showcase the highlight style.

    Returns:
        Dict matching the /api/pump-trending schema with sample data.
    """
    now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    sample = [
        {"symbol": "DOGEGECKO", "name": "DogeGecko",  "mc": 62_000_000,  "vol": 1_800_000, "score": 92.3, "ago": "6 min"},
        {"symbol": "BONK",      "name": "Bonk",       "mc": 48_500_000,  "vol":   892_000, "score": 88.1, "ago": "8 min"},
        {"symbol": "TROLL",     "name": "Troll",      "mc": 37_389_476,  "vol":    12_984, "score": 80.6, "ago": "12 min"},
        {"symbol": "BOME",      "name": "Book of Memecoin", "mc": 22_100_000, "vol": 156_000, "score": 76.3, "ago": "18 min"},
        {"symbol": "WIF",       "name": "Dogwifhat",  "mc": 1_880_000_000, "vol": 2_100_000, "score": 72.1, "ago": "5 min"},
        {"symbol": "PEPE",      "name": "Pepe",       "mc":   750_000_000, "vol":   880_000, "score": 61.4, "ago": "25 min"},
        {"symbol": "FLOKI",     "name": "Floki",      "mc": 1_100_000_000, "vol":   450_000, "score": 55.7, "ago": "32 min"},
        {"symbol": "POGAI",     "name": "PogAI",      "mc":     2_400_000, "vol":     7_200, "score": 44.2, "ago": "41 min"},
    ]
    tokens: List[Dict[str, Any]] = []
    for s in sample:
        tokens.append({
            "symbol": s["symbol"],
            "name": s["name"],
            "price": round(s["mc"] / _PUMP_SUPPLY, 8),
            "momentum": s["score"],
            "launched": f"{s['ago']} ago",
            "marketCapUsd": round(s["mc"], 2),
            "volumeUsd": round(s["vol"], 2),
            "url": f"https://pump.fun/s/{s['symbol']}",
        })
    return {
        "tokens": tokens,
        "window": "1h",
        "ts": now_ts,
        "sources": ["pumpfun", "mock"],
        "note": "Showing sample data — live API unavailable.",
        "count": len(tokens),
    }


@app.route("/api/pump-trending")
def api_pump_trending():
    """Trending Pump.fun tokens (1h window) from the Three.ws API.

    Fetches live data from the free Three.ws API and normalizes it into a
    compact schema (symbol, price, momentum 0-100, launched, market cap,
    volume). On any upstream failure returns branded mock data so the
    section always renders. Refreshed by the frontend every 60 seconds.

    Returns:
        JSON: {"tokens": [...], "window", "ts", "sources", "note", "count"}
    """
    try:
        return jsonify(_threews_pump_tokens())
    except Exception as exc:  # noqa: BLE001 — never break the homepage
        log.warning("Pump trending: Three.ws fetch failed (%s) — serving mock data", exc)
        return jsonify(_mock_pump_tokens())


@app.route("/api/waitlist", methods=["POST"])
def api_waitlist():
    """Add a subscriber to the waitlist.

    Form fields:
        email (required), name (optional), referred_by (optional).

    Returns:
        JSON: {"success": bool, "referral_code": str, "error": str?}
    """
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    referred_by = (request.form.get("referred_by") or "").strip()

    if not email or not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Please enter a valid email."}), 400

    db = _db()
    try:
        subscriber = db.add_subscriber(email, name=name, referred_by=referred_by)
        log.info("New waitlist subscriber: %s", email)
        return jsonify({
            "success": True,
            "referral_code": subscriber.get("referral_code", ""),
        })
    except Exception as exc:  # noqa: BLE001
        log.error("Waitlist signup failed: %s", exc)
        return jsonify({"success": False, "error": "Could not add you to the list."}), 500


@app.route("/api/newsletter", methods=["POST"])
def api_newsletter():
    """Subscribe an email to the newsletter (reuses waitlist table).

    Form fields:
        email (required).

    Returns:
        JSON: {"success": bool, "error": str?}
    """
    email = (request.form.get("email") or "").strip().lower()
    if not email or not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Please enter a valid email."}), 400

    db = _db()
    try:
        db.add_subscriber(email)
        log.info("Newsletter subscription: %s", email)
        return jsonify({"success": True})
    except Exception as exc:  # noqa: BLE001
        log.error("Newsletter subscribe failed: %s", exc)
        return jsonify({"success": False, "error": "Could not subscribe."}), 500


# ---------------------------------------------------------------------------
# Stripe webhook (production payments)
# ---------------------------------------------------------------------------

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events (subscriptions, payments).

    Verifies the signature using STRIPE_WEBHOOK_SECRET, then records the
    event in financial_records. Returns 200 to acknowledge receipt.

    Returns:
        JSON: {"received": True} on success, 400 on verification failure.
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        from config.stripe_config import verify_webhook
        event = verify_webhook(payload, sig_header)
    except Exception as exc:  # noqa: BLE001
        log.error("Stripe webhook verification failed: %s", exc)
        return jsonify({"error": "invalid signature"}), 400

    event_type = event.get("type", "unknown")
    log.info("Stripe webhook received: %s", event_type)

    db = _db()
    # Record revenue for relevant events
    if event_type in {"checkout.session.completed", "invoice.paid"}:
        data = event.get("data", {}).get("object", {})
        amount = data.get("amount_total") or data.get("amount_paid") or 0
        db.add_financial(
            "revenue", "stripe",
            float(amount) / 100.0,  # Stripe amounts are in cents
            f"stripe:{event_type}",
        )
        log.info("Stripe revenue recorded: $%.2f", float(amount) / 100.0)

    return jsonify({"received": True})


# ---------------------------------------------------------------------------
# Patreon webhook (patron membership)
# ---------------------------------------------------------------------------

@app.route("/api/patreon/webhook", methods=["POST"])
def patreon_webhook():
    """Handle Patreon webhook events (members:create / update / delete).

    Verifies the HMAC-SHA1 signature from the X-Patreon-Signature header,
    fetches full patron details from the Patreon API, and upserts them into
    the patrons table.

    Returns:
        JSON: {"received": True} on success, 400 on verification failure.
    """
    payload = request.get_data()
    signature = request.headers.get("X-Patreon-Signature", "")

    from src.patreon.webhook import verify_signature, parse_event
    if not verify_signature(payload, signature):
        log.error("Patreon webhook signature verification failed")
        return jsonify({"error": "invalid signature"}), 400

    event = parse_event(payload)
    if not event:
        log.warning("Patreon webhook could not be parsed")
        return jsonify({"received": True}), 200  # ack to avoid retries

    db = _db()
    event_type = event["event"]
    member_id = event["member_id"]
    patron = event.get("patron")

    log.info("Patreon webhook: %s for member %s", event_type, member_id)

    if event_type == "members:delete":
        db.delete_patron(member_id)
    elif patron:
        # Normalize status: Patreon uses 'active_patron' | 'former_patron' | 'declined_patron'
        raw_status = patron.get("status", "active_patron")
        status = {
            "active_patron": "active",
            "former_patron": "canceled",
            "declined_patron": "expired",
        }.get(raw_status, "active")
        db.upsert_patron({
            "patreon_id": patron.get("patreon_id") or member_id,
            "email": patron.get("email"),
            "full_name": patron.get("full_name"),
            "tier": patron.get("tier"),
            "tier_level": patron.get("tier_level"),
            "status": status,
        })
        log.info("Patreon patron stored: %s (tier %s)", member_id, patron.get("tier_level"))
    else:
        log.warning("Patreon webhook: no patron details fetched for %s", member_id)

    return jsonify({"received": True})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_title(post: Dict[str, Any]) -> str:
    """Derive a display title from a post.

    Args:
        post: Post row dict.

    Returns:
        A short title string.
    """
    content = post.get("content", "")
    # First line, truncated
    first_line = content.splitlines()[0] if content else "Untitled"
    return first_line[:60] + ("..." if len(first_line) > 60 else "")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_e: Any):
    """Render a friendly 404 page."""
    return render_template("base.html"), 404


@app.errorhandler(500)
def server_error(_e: Any):
    """Render a friendly 500 page."""
    return render_template("base.html"), 500


# ---------------------------------------------------------------------------
# Ping endpoints for uptime monitoring and task triggering
# ---------------------------------------------------------------------------

import os
import subprocess
import sys
import threading
import time
from typing import List, Optional

#: Absolute path to main.py (the CLI orchestrator)
_MAIN_PATH = os.path.join(os.path.dirname(__file__), "..", "main.py")

#: Default timeout per task (seconds)
_TASK_TIMEOUT = 120

#: Agent definitions: name -> (CLI args, description, recommended frequency)
AGENT_TASKS: Dict[str, Dict[str, Any]] = {
    "scout": {
        "args": ["--run-scout"],
        "description": "Scrape crypto trends (Twitter, Pump.fun, CMC, DEXScreener, Reddit)",
        "frequency": "Every 4 hours",
    },
    "chronicler": {
        "args": ["--run-chronicle", "--chronicle-mode", "archive"],
        "description": "Archive data + financial tracking to JSON/SQLite",
        "frequency": "Every 6 hours",
    },
    "watchtower": {
        "args": ["--run-watchtower"],
        "description": "Health monitoring (API, DB, social, website, logs)",
        "frequency": "Every 30 minutes",
    },
    "social": {
        "args": ["--run-social"],
        "description": "Post to Twitter/X (The Radar)",
        "frequency": "Every 4 hours",
    },
    "mechanic": {
        "args": ["--run-mechanic"],
        "description": "Self-healing (retry posts, reconnect DB, rotate keys)",
        "frequency": "Every 1 hour",
    },
    "forge": {
        "args": ["--run-forge", "--type", "brand"],
        "description": "Image generation (DALL-E 3 or SVG fallback)",
        "frequency": "On-demand",
    },
}


def _run_single_task(name: str, timeout: int = _TASK_TIMEOUT) -> Dict[str, Any]:
    """Run a single agent task via subprocess.

    Args:
        name: Agent name (must be in AGENT_TASKS).
        timeout: Max seconds before the task is killed.

    Returns:
        Dict: {"task": name, "status": "success"|"failed"|"timeout",
               "returncode": int|None, "duration": float, "error": str|None}
    """
    spec = AGENT_TASKS.get(name)
    if not spec:
        return {"task": name, "status": "failed", "returncode": None,
                "duration": 0.0, "error": f"unknown task: {name}"}

    start = time.time()
    log.info("[PING] Task '%s' starting", name)
    try:
        result = subprocess.run(
            [sys.executable, _MAIN_PATH] + spec["args"],
            capture_output=True,
            timeout=timeout,
        )
        duration = time.time() - start
        status = "success" if result.returncode == 0 else "failed"
        log.info("[PING] Task '%s' %s (returncode=%s, %.1fs)",
                 name, status, result.returncode, duration)
        return {
            "task": name,
            "status": status,
            "returncode": result.returncode,
            "duration": round(duration, 2),
            "error": None,
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        log.error("[PING] Task '%s' timed out after %.1fs", name, duration)
        return {
            "task": name,
            "status": "timeout",
            "returncode": None,
            "duration": round(duration, 2),
            "error": f"timed out after {timeout}s",
        }
    except Exception as exc:  # noqa: BLE001
        duration = time.time() - start
        log.error("[PING] Task '%s' failed: %s", name, exc)
        return {
            "task": name,
            "status": "failed",
            "returncode": None,
            "duration": round(duration, 2),
            "error": str(exc),
        }


def _run_tasks_in_background(task_names: List[str]) -> None:
    """Run a list of agent tasks sequentially in a background thread.

    Each task is isolated — a failure in one never stops the others.

    Args:
        task_names: List of agent names to run in order.
    """
    def runner() -> None:
        for name in task_names:
            _run_single_task(name)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()


def _ping_response(task_names: List[str]) -> Any:
    """Build the JSON response for a ping endpoint.

    Args:
        task_names: List of agent names being triggered.

    Returns:
        Flask JSON response with a confirmation + task summary.
    """
    log.info("Ping received — triggering tasks: %s", ", ".join(task_names))
    _run_tasks_in_background(task_names)
    return jsonify({
        "pong": True,
        "triggered": task_names,
        "message": "Tasks triggered in background.",
        "note": "Use /ping/help for all endpoints and recommended frequencies.",
    })


@app.route("/ping")
def ping():
    """Trigger ALL agents in the background (Scout → Chronicler → Watchtower → Social → Mechanic).

    Returns:
        JSON confirmation with the list of triggered tasks.
    """
    return _ping_response(["scout", "chronicler", "watchtower", "social", "mechanic"])


@app.route("/ping/all")
def ping_all():
    """Trigger ALL agents (same as /ping)."""
    return _ping_response(["scout", "chronicler", "watchtower", "social", "mechanic"])


@app.route("/ping/scout")
def ping_scout():
    """Trigger only The Scout (scrape trends)."""
    return _ping_response(["scout"])


@app.route("/ping/chronicler")
def ping_chronicler():
    """Trigger only The Chronicler (archive + financials)."""
    return _ping_response(["chronicler"])


@app.route("/ping/watchtower")
def ping_watchtower():
    """Trigger only The Watchtower (health check)."""
    return _ping_response(["watchtower"])


@app.route("/ping/social")
def ping_social():
    """Trigger only The Social agent (post to Twitter)."""
    return _ping_response(["social"])


@app.route("/ping/mechanic")
def ping_mechanic():
    """Trigger only The Mechanic (self-healing)."""
    return _ping_response(["mechanic"])


@app.route("/ping/forge")
def ping_forge():
    """Trigger only The Forge (image generation)."""
    return _ping_response(["forge"])


@app.route("/ping/help")
def ping_help():
    """Documentation page listing all ping endpoints and recommended frequencies.

    Returns:
        JSON with all endpoints, descriptions, and recommended frequencies.
    """
    endpoints = []
    for name, spec in AGENT_TASKS.items():
        endpoints.append({
            "endpoint": f"/ping/{name}",
            "task": name,
            "description": spec["description"],
            "recommended_frequency": spec["frequency"],
        })
    endpoints.append({
        "endpoint": "/ping",
        "task": "all",
        "description": "Trigger ALL agents (Scout → Chronicler → Watchtower → Social → Mechanic)",
        "recommended_frequency": "Every 30 minutes (keep-alive)",
    })
    endpoints.append({
        "endpoint": "/ping/all",
        "task": "all",
        "description": "Same as /ping — trigger ALL agents",
        "recommended_frequency": "Every 30 minutes (keep-alive)",
    })
    endpoints.append({
        "endpoint": "/ping/help",
        "task": "docs",
        "description": "This documentation page",
        "recommended_frequency": "As needed",
    })

    return jsonify({
        "service": "OracleForge Studios",
        "endpoints": endpoints,
        "uptimerobot_recommendations": [
            {"endpoint": "/ping/watchtower", "purpose": "Health monitoring", "frequency": "Every 30 minutes"},
            {"endpoint": "/ping/scout", "purpose": "Scrape trends", "frequency": "Every 4 hours"},
            {"endpoint": "/ping/social", "purpose": "Post to Twitter", "frequency": "Every 4 hours"},
            {"endpoint": "/ping/chronicler", "purpose": "Archive data", "frequency": "Every 6 hours"},
            {"endpoint": "/ping/mechanic", "purpose": "Self-healing", "frequency": "Every 1 hour"},
            {"endpoint": "/ping/forge", "purpose": "Image generation", "frequency": "On-demand"},
        ],
    })