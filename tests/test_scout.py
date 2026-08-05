"""Tests for The Scout scraping agents."""

from __future__ import annotations

import pytest

from src.agents.scout import _trend, _mock_twitter_data, run_scout


def test_trend_normalization():
    """_trend() should produce a normalized dict with defaults."""
    t = _trend("pumpfun", "MOON", "MoonCoin", price=0.5, change_pct=10.0)
    assert t["source"] == "pumpfun"
    assert t["token_symbol"] == "MOON"
    assert t["token_name"] == "MoonCoin"
    assert t["price"] == 0.5
    assert t["price_change_pct"] == 10.0
    assert t["volume_24h"] == 0.0
    assert t["market_cap"] == 0.0
    assert t["rank"] == 0
    assert t["captured_at"]


def test_trend_symbol_uppercased():
    """Symbols should be uppercased and truncated to 32 chars."""
    t = _trend("cmc", "doge", "Dogecoin")
    assert t["token_symbol"] == "DOGE"


def test_mock_twitter_data():
    """Mock Twitter data should include trends and celebrity posts."""
    data = _mock_twitter_data()
    assert "trends" in data
    assert "celebrity_posts" in data
    assert len(data["trends"]) > 0
    assert len(data["celebrity_posts"]) > 0
    # Celebrity posts must have required keys
    for celeb in data["celebrity_posts"]:
        assert "celebrity_name" in celeb
        assert "post_text" in celeb
        assert "topic_hint" in celeb


@pytest.mark.asyncio
async def test_run_scout_stores_trends(db):
    """run_scout() should store trends to the DB (twitter mock only)."""
    result = await run_scout(sources="twitter", db=db)
    assert result["trends"] > 0
    assert result["celebrity_posts"] > 0
    # Verify DB has the rows
    trends = db.latest_trends(limit=10)
    assert len(trends) == result["trends"]
    celebs = db.unengaged_celebrity_posts(limit=10)
    assert len(celebs) == result["celebrity_posts"]