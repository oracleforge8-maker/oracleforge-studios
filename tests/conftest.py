"""Shared pytest fixtures for OracleForge tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def db(tmp_path):
    """Provide an isolated in-memory/temp Database instance per test."""
    from src.database import Database
    test_db = Database(db_path=tmp_path / "test_chronicler.db")
    yield test_db
    test_db.close()


@pytest.fixture
def sample_trends():
    """Return a list of normalized trend dicts for tests."""
    from src.utils import utcnow
    return [
        {
            "source": "twitter_mock",
            "token_symbol": "DOGE",
            "token_name": "Dogecoin",
            "price": 0.32,
            "price_change_pct": 12.4,
            "volume_24h": 1_200_000_000,
            "market_cap": 45_000_000_000,
            "rank": 1,
            "url": "https://x.com/search?q=%23DOGE",
            "raw_data": None,
            "captured_at": utcnow(),
        },
        {
            "source": "pumpfun",
            "token_symbol": "MOON",
            "token_name": "MoonCoin",
            "price": 0.0045,
            "price_change_pct": 145.0,
            "volume_24h": 50_000_000,
            "market_cap": 45_000_000,
            "rank": 2,
            "url": "https://pump.fun/coin/mock",
            "raw_data": None,
            "captured_at": utcnow(),
        },
    ]