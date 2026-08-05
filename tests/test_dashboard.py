"""Tests for the Observatory dashboard server."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config

#: Test dashboard credentials (override env for the test session)
TEST_USER = "testadmin"
TEST_PASS = "testpass123"


@pytest.fixture
def dash_client(monkeypatch, db):
    """Provide a Flask test client for the dashboard with test creds.

    Patches ``server._db`` so API routes read from the test DB rather than
    the production singleton.
    """
    monkeypatch.setenv("DASHBOARD_USER", TEST_USER)
    monkeypatch.setenv("DASHBOARD_PASSWORD", TEST_PASS)
    from src.dashboard import blueprint
    blueprint._db = lambda: db  # type: ignore[assignment]
    # Reset the module-level vault singleton so each test starts locked
    blueprint._VAULT = None  # type: ignore[attr-defined]
    from src.dashboard import server
    server.app.config["TESTING"] = True
    server.app.config["SECRET_KEY"] = "test-secret"
    return server.app.test_client()


def _login(client):
    """Log into the dashboard test client."""
    return client.post("/dashboard/login", data={
        "username": TEST_USER,
        "password": TEST_PASS,
    }, follow_redirects=True)


def test_login_page_renders(dash_client):
    """Login page should render 200."""
    resp = dash_client.get("/dashboard/login")
    assert resp.status_code == 200
    assert b"OracleForge" in resp.data


def test_login_success(dash_client):
    """Valid credentials should log in and reach the overview."""
    resp = _login(dash_client)
    assert resp.status_code == 200


def test_login_failure(dash_client):
    """Invalid credentials should 401."""
    resp = dash_client.post("/dashboard/login", data={
        "username": "bad",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_dashboard_requires_auth(dash_client):
    """Dashboard pages should redirect when not authenticated."""
    resp = dash_client.get("/dashboard")
    assert resp.status_code == 302  # redirect to login


def test_dashboard_pages_renders(dash_client):
    """All 7 dashboard pages should render 200 when authenticated."""
    _login(dash_client)
    pages = [
        "/dashboard",
        "/dashboard/health",
        "/dashboard/activity",
        "/dashboard/controls",
        "/dashboard/finance",
        "/dashboard/vault",
        "/dashboard/settings",
    ]
    for page in pages:
        resp = dash_client.get(page)
        assert resp.status_code == 200, f"{page} returned {resp.status_code}"


def test_api_health_requires_auth(dash_client):
    """Health API should reject unauthenticated requests."""
    resp = dash_client.get("/api/dashboard/health/latest")
    assert resp.status_code == 302


def test_api_controls(dash_client, db):
    """Controls API should return agent states."""
    _login(dash_client)
    resp = dash_client.get("/api/dashboard/controls")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "agents" in data
    assert "scout" in data["agents"]


def test_api_controls_pause_resume(dash_client, db):
    """Pause and resume should update agent state."""
    _login(dash_client)
    resp = dash_client.post("/api/dashboard/controls/pause",
                            json={"agent": "scout"})
    assert resp.get_json()["state"] == "paused"
    assert db.get_setting("agent_scout_state") == "paused"

    resp = dash_client.post("/api/dashboard/controls/resume",
                            json={"agent": "scout"})
    assert resp.get_json()["state"] == "running"


def test_api_controls_unknown_agent(dash_client):
    """Unknown agent should 400."""
    _login(dash_client)
    resp = dash_client.post("/api/dashboard/controls/pause",
                            json={"agent": "nope"})
    assert resp.status_code == 400


def test_api_finance(dash_client, db):
    """Finance API should return summary + recent records."""
    db.add_financial("cost", "openrouter", 0.001, "test")
    _login(dash_client)
    resp = dash_client.get("/api/dashboard/finance")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data
    assert "recent" in data
    assert len(data["recent"]) >= 1


def test_api_vault_unlock_creates(dash_client, tmp_path, monkeypatch):
    """Vault unlock should initialize a new vault on first use."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "test_vault.enc"))
    _login(dash_client)
    resp = dash_client.post("/api/dashboard/vault/unlock",
                            json={"master_password": "master123"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data.get("initialized") is True


def test_api_settings(dash_client, db):
    """Settings API should return system info."""
    _login(dash_client)
    resp = dash_client.get("/api/dashboard/settings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "site_url" in data
    assert "subscriber_count" in data


def test_activity_api(dash_client, db):
    """Activity API should return posts, repairs, and escalations."""
    db.create_post("twitter", "gm anon", post_type="radar", status="posted")
    _login(dash_client)
    resp = dash_client.get("/api/dashboard/activity")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "activity" in data
    assert len(data["activity"]) >= 1


def test_api_config_masked(dash_client):
    """Config API should return masked secrets, never full values."""
    _login(dash_client)
    resp = dash_client.get("/api/dashboard/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "env_path" in data
    assert "keys" in data
    assert "counts" in data

    # Find the OpenRouter key entry — its value must be masked
    openrouter = next((k for k in data["keys"] if k["key"] == "OPENROUTER_API_KEY"), None)
    if openrouter and openrouter["set"]:
        assert openrouter["secret"] is True
        # Masked value must not equal the full value
        assert openrouter["masked"] != openrouter["value"]
        assert "••••••••" in openrouter["masked"]


def test_api_config_requires_auth(dash_client):
    """Config API should reject unauthenticated requests."""
    resp = dash_client.get("/api/dashboard/config")
    assert resp.status_code == 302


def test_api_vault_import_env_locked(dash_client):
    """Import .env should fail when the vault is locked."""
    _login(dash_client)
    resp = dash_client.post("/api/dashboard/vault/import-env")
    assert resp.status_code == 401
    assert resp.get_json()["error"]


def test_api_vault_import_env(dash_client, tmp_path, monkeypatch):
    """Import .env should store keys in the encrypted vault."""
    # Point the vault at a temp path and initialize it
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "test_vault.enc"))
    _login(dash_client)
    resp = dash_client.post("/api/dashboard/vault/unlock",
                            json={"master_password": "master123"})
    assert resp.get_json()["success"] is True

    # Import the real .env
    resp = dash_client.post("/api/dashboard/vault/import-env")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["imported"] > 0
