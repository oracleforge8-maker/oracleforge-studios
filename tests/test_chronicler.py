"""Tests for The Chronicler archival/reporting agents."""

from __future__ import annotations

import json

import pytest

from src.agents.chronicler import archive_daily, collect_snapshot, financial_snapshot


def test_collect_snapshot(db, sample_trends):
    """collect_snapshot() should include all tables."""
    db.insert_trends(sample_trends)
    db.create_post("twitter", "gm anon 🚀", post_type="radar", status="mock")
    db.add_subscriber("test@example.com", name="Tester")

    snapshot = collect_snapshot(db)
    assert "trends" in snapshot
    assert "posts" in snapshot
    assert "subscribers" in snapshot
    assert "financial_records" in snapshot
    assert "celebrity_posts" in snapshot
    assert "replies" in snapshot
    assert len(snapshot["trends"]) == 2
    assert len(snapshot["posts"]) == 1
    assert len(snapshot["subscribers"]) == 1


def test_archive_daily_writes_json(db, sample_trends, tmp_path):
    """archive_daily() should write a snapshot.json to the archive path."""
    db.insert_trends(sample_trends)
    result = archive_daily(db)
    assert "path" in result
    assert "counts" in result
    assert result["counts"]["trends"] == 2

    # Verify the file exists and is valid JSON
    path = tmp_path / "archive" / "snapshot.json"
    # archive_daily uses the env ARCHIVE_PATH; verify via the returned path
    from pathlib import Path
    snapshot_path = Path(result["path"])
    assert snapshot_path.exists()
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert "trends" in data


def test_financial_snapshot(db):
    """financial_snapshot() should persist a financial summary."""
    db.add_financial("cost", "openrouter", 0.001, "test call")
    db.add_financial("revenue", "stripe", 20.0, "test sub")
    summary = financial_snapshot(db)
    assert summary["cost"] == pytest.approx(0.001)
    assert summary["revenue"] == pytest.approx(20.0)
    assert summary["net"] == pytest.approx(19.999)