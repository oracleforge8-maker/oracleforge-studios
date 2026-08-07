"""Tests for the OracleForge Flask web server."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(db, monkeypatch):
    """Provide a Flask test client isolated to the test database.

    Patches ``web.server._db`` so API routes read from the test DB
    rather than the production singleton.
    """
    import web.server as server
    server._db = lambda: db  # type: ignore[assignment]
    server.app.config["TESTING"] = True
    return server.app.test_client()


def test_home_page(client):
    """Home page should render 200 with brand content."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"OracleForge" in resp.data
    assert b"Intelligence Engine" in resp.data


def test_all_pages_render(client):
    """All marketing pages should return 200."""
    for route in ["/tools", "/live-demo", "/pricing", "/blog", "/about", "/waitlist"]:
        resp = client.get(route)
        assert resp.status_code == 200, f"{route} returned {resp.status_code}"


def test_api_trends(client, db, sample_trends):
    """GET /api/trends should return stored trends as JSON."""
    db.insert_trends(sample_trends)
    resp = client.get("/api/trends?limit=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "trends" in data
    assert len(data["trends"]) == 2


def test_api_ticker(client):
    """GET /api/ticker returns the ticker schema (prices + top-3 gainers).

    No COINGECKO_API_KEY is set in the test env, so the endpoint serves the
    branded mock data — keeping the test fast and network-free.
    """
    resp = client.get("/api/ticker")
    assert resp.status_code == 200
    data = resp.get_json()

    for key in ("btc", "eth", "sol"):
        assert key in data
        assert isinstance(data[key]["price"], (int, float))
        assert isinstance(data[key]["change_24h"], (int, float))

    assert isinstance(data["top_gainers"], list)
    assert len(data["top_gainers"]) == 3
    for i, g in enumerate(data["top_gainers"], start=1):
        assert g["rank"] == i
        assert g["symbol"]
        assert isinstance(g["price"], (int, float))
        assert isinstance(g["change_30m"], (int, float))


def test_api_top_gainers(client):
    """GET /api/top-gainers returns the 10-coin gainers schema.

    No COINGECKO_API_KEY is set in the test env, so the endpoint serves the
    branded mock data — keeping the test fast and network-free.
    """
    resp = client.get("/api/top-gainers")
    assert resp.status_code == 200
    data = resp.get_json()

    assert isinstance(data, list)
    assert len(data) == 10
    for i, g in enumerate(data, start=1):
        assert g["rank"] == i
        assert g["symbol"]
        assert isinstance(g["price"], (int, float))
        assert isinstance(g["change_30m"], (int, float))
        assert isinstance(g["change_24h"], (int, float))


def test_api_pump_trending(client, monkeypatch):
    """GET /api/pump-trending returns the normalized Pump.fun schema.

    The endpoint normally calls the free Three.ws API live. In the test
    environment we force the mock-fallback path (by making the live fetch
    raise) so the test is deterministic and network-free, while still
    validating the response shape the frontend depends on.
    """
    import web.server as server

    def _always_fail(*args, **kwargs):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(server, "_threews_pump_tokens", _always_fail)

    resp = client.get("/api/pump-trending")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "tokens" in data
    assert isinstance(data["tokens"], list)
    assert data["window"]
    assert data["count"] == len(data["tokens"])
    for token in data["tokens"]:
        assert token["symbol"]
        assert isinstance(token["price"], (int, float))
        assert isinstance(token["momentum"], (int, float))
        assert 0 <= token["momentum"] <= 100
        assert token["launched"]


def test_api_waitlist_valid(client, db):
    """POST /api/waitlist with a valid email should succeed."""
    resp = client.post("/api/waitlist", data={"email": "anon@example.com"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["referral_code"].startswith("OF-")


def test_api_waitlist_invalid(client):
    """POST /api/waitlist with an invalid email should 400."""
    resp = client.post("/api/waitlist", data={"email": "not-an-email"})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_api_newsletter(client, db):
    """POST /api/newsletter should subscribe an email."""
    resp = client.post("/api/newsletter", data={"email": "news@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True