"""Tests for the Patreon integration (tiers, webhook, database patrons)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from src.patreon import tiers
from src.patreon import webhook
from src.patreon import client


# ---------------------------------------------------------------------------
# Tier mapping
# ---------------------------------------------------------------------------

def test_tier_by_name_exact():
    """Exact tier names should map to levels."""
    assert tiers.tier_by_name("Forge Supporter") == 1
    assert tiers.tier_by_name("Meme Master") == 2
    assert tiers.tier_by_name("Forge Master") == 3


def test_tier_by_name_case_insensitive():
    """Tier matching should be case-insensitive."""
    assert tiers.tier_by_name("meme master") == 2
    assert tiers.tier_by_name("FORGE MASTER") == 3


def test_tier_by_name_fuzzy():
    """Fuzzy keyword matching should work for partial names."""
    assert tiers.tier_by_name("Meme Master Tier") == 2
    assert tiers.tier_by_name("Forge Master Plus") == 3
    assert tiers.tier_by_name("Supporter") == 1


def test_tier_by_name_unknown():
    """Unknown tier names should return None."""
    assert tiers.tier_by_name("") is None
    assert tiers.tier_by_name("Random Tier") is None


def test_tier_info():
    """tier_info should return metadata for a level."""
    info = tiers.tier_info(2)
    assert info["name"] == "Meme Master"
    assert info["level"] == 2
    assert "Weekly PDF reports" in info["benefits"]


def test_all_tiers_sorted():
    """all_tiers should return tiers sorted by level."""
    all_t = tiers.all_tiers()
    assert [t["level"] for t in all_t] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def test_verify_signature_valid(monkeypatch):
    """A correctly-signed payload should verify."""
    monkeypatch.setenv("PATREON_WEBHOOK_SECRET", "test-secret")
    payload = b'{"data": {"type": "members:create", "id": "123"}}'
    sig = hmac.new(b"test-secret", payload, hashlib.sha1).hexdigest()
    assert webhook.verify_signature(payload, sig) is True


def test_verify_signature_invalid(monkeypatch):
    """A wrong signature should fail verification."""
    monkeypatch.setenv("PATREON_WEBHOOK_SECRET", "test-secret")
    payload = b'{"data": {"type": "members:create", "id": "123"}}'
    assert webhook.verify_signature(payload, "wrong-signature") is False


def test_verify_signature_no_secret(monkeypatch):
    """Missing webhook secret should fail verification."""
    monkeypatch.delenv("PATREON_WEBHOOK_SECRET", raising=False)
    assert webhook.verify_signature(b"{}", "anything") is False


def test_parse_event_valid(monkeypatch):
    """A valid members:create event should parse."""
    monkeypatch.setenv("PATREON_ACCESS_TOKEN", "test-token")
    payload = json.dumps({"data": {"type": "members:create", "id": "member-1"}}).encode()
    # get_patron will fail (no real API) but parse_event should still return the event
    event = webhook.parse_event(payload)
    assert event is not None
    assert event["event"] == "members:create"
    assert event["member_id"] == "member-1"


def test_parse_event_unsupported():
    """Unsupported event types should return None."""
    payload = json.dumps({"data": {"type": "pledges:create", "id": "1"}}).encode()
    assert webhook.parse_event(payload) is None


def test_parse_event_malformed():
    """Malformed payloads should return None."""
    assert webhook.parse_event(b"not-json") is None


# ---------------------------------------------------------------------------
# Database patrons
# ---------------------------------------------------------------------------

def test_upsert_patron(db):
    """upsert_patron should insert a new patron."""
    patron = db.upsert_patron({
        "patreon_id": "patron-1",
        "email": "patron@example.com",
        "full_name": "Test Patron",
        "tier": "Meme Master",
        "tier_level": 2,
        "status": "active",
    })
    assert patron["patreon_id"] == "patron-1"
    assert patron["tier_level"] == 2
    assert db.patron_total_active() == 1


def test_upsert_patron_update(db):
    """upsert_patron should update an existing patron."""
    db.upsert_patron({
        "patreon_id": "patron-1",
        "email": "patron@example.com",
        "tier": "Forge Supporter",
        "tier_level": 1,
        "status": "active",
    })
    db.upsert_patron({
        "patreon_id": "patron-1",
        "email": "patron@example.com",
        "tier": "Forge Master",
        "tier_level": 3,
        "status": "active",
    })
    patron = db.get_patron("patron-1")
    assert patron["tier_level"] == 3
    assert db.patron_total_active() == 1  # still one patron


def test_patron_counts_by_tier(db):
    """patron_counts_by_tier should group active patrons by level."""
    db.upsert_patron({"patreon_id": "p1", "tier_level": 1, "status": "active"})
    db.upsert_patron({"patreon_id": "p2", "tier_level": 2, "status": "active"})
    db.upsert_patron({"patreon_id": "p3", "tier_level": 2, "status": "active"})
    db.upsert_patron({"patreon_id": "p4", "tier_level": 3, "status": "canceled"})
    counts = db.patron_counts_by_tier()
    assert counts.get(1) == 1
    assert counts.get(2) == 2
    assert counts.get(3) is None  # canceled not counted


def test_delete_patron(db):
    """delete_patron should remove a patron."""
    db.upsert_patron({"patreon_id": "p1", "tier_level": 1, "status": "active"})
    assert db.delete_patron("p1") is True
    assert db.get_patron("p1") is None
    assert db.delete_patron("p1") is False


def test_list_patrons_filter(db):
    """list_patrons should filter by status."""
    db.upsert_patron({"patreon_id": "p1", "tier_level": 1, "status": "active"})
    db.upsert_patron({"patreon_id": "p2", "tier_level": 2, "status": "canceled"})
    active = db.list_patrons(status="active")
    assert len(active) == 1
    assert active[0]["patreon_id"] == "p1"


# ---------------------------------------------------------------------------
# Client normalization
# ---------------------------------------------------------------------------

def test_client_normalize_member():
    """_normalize_member should build a patron dict from JSON:API."""
    payload = {
        "data": {
            "id": "m1",
            "type": "member",
            "attributes": {"full_name": "Jane", "email": "jane@x.com", "patron_status": "active_patron"},
            "relationships": {
                "currently_entitled_tiers": {"data": [{"id": "t2"}]},
                "user": {"data": {"id": "u1"}},
            },
        },
        "included": [
            {"id": "t2", "type": "tier", "attributes": {"title": "Meme Master"}},
            {"id": "u1", "type": "user", "attributes": {"email": "jane@x.com"}},
        ],
    }
    patron = client._normalize_member(payload)
    assert patron is not None
    assert patron["patreon_id"] == "m1"
    assert patron["tier_level"] == 2
    assert patron["tier"] == "Meme Master"
    assert patron["email"] == "jane@x.com"