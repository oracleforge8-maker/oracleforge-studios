"""Tests for The Watchtower health monitoring + The Mechanic repair engine."""

from __future__ import annotations

import pytest

from src.watchtower import health_checker, reporter
from src.mechanic import repair_engine, escalation_manager


def test_check_database(db):
    """Database check should report all required tables present."""
    cfg = {"database": {"required_tables": [
        "trends", "posts", "subscribers", "financial_records",
        "celebrity_posts", "replies", "settings",
    ]}}
    results = health_checker.check_database(db, cfg)
    assert results[0]["level"] == "ok"


def test_check_database_missing_table(db):
    """Database check should flag missing tables as critical."""
    cfg = {"database": {"required_tables": ["trends", "missing_table_xyz"]}}
    results = health_checker.check_database(db, cfg)
    assert any(r["level"] == "critical" for r in results)


def test_check_social_posts_empty(db):
    """Social check with no posts should warn."""
    cfg = {"social": {"platforms": ["twitter"], "check_last_posts": 3}}
    results = health_checker.check_social_posts(db, cfg)
    assert results[0]["name"] == "social:twitter"
    assert results[0]["level"] == "warning"


def test_check_social_posts_failed(db):
    """Social check with failed posts should warn."""
    db.create_post("twitter", "test", post_type="radar", status="failed")
    cfg = {"social": {"platforms": ["twitter"], "check_last_posts": 3}}
    results = health_checker.check_social_posts(db, cfg)
    assert results[0]["level"] == "warning"
    assert "failed" in results[0]["detail"]


def test_check_logs_missing_dir():
    """Log check should warn if no log directory exists."""
    from src import config
    old = config.env("LOG_PATH", "logs")
    # Point at a non-existent dir via env monkeypatch (module reads at call time)
    import os
    os.environ["LOG_PATH"] = str(config.PROJECT_ROOT / "logs-nonexistent")
    try:
        results = health_checker.check_logs({})
        assert results[0]["level"] == "warning"
    finally:
        os.environ["LOG_PATH"] = old


def test_report_save_load(db, tmp_path):
    """Reporter should save and load history."""
    report = {"generated_at": "2026-01-01T00:00:00Z", "overall": "ok",
              "summary": {"total": 3, "ok": 3, "warning": 0, "critical": 0}}
    reporter.save_report(report)
    history = reporter.load_history(limit=5)
    assert len(history) >= 1
    assert history[0]["overall"] == "ok"


def test_mechanic_repairs_failed_posts(db):
    """Mechanic should reset failed posts to draft."""
    db.create_post("twitter", "broken post", post_type="radar", status="failed")
    report = {
        "checks": [
            {"name": "social:twitter", "level": "warning", "detail": "1 failed"},
        ]
    }
    summary = repair_engine.run_mechanic(report, db=db)
    assert any("retry_posts" in r["repair"] for r in summary["repairs"])
    # The failed post should now be a draft
    posts = db.query("SELECT * FROM posts WHERE platform='twitter'")
    assert posts[0]["status"] == "draft"


def test_mechanic_escalates_no_backup_key(db):
    """Mechanic should escalate when no backup API key exists."""
    report = {
        "checks": [
            {"name": "api:openrouter", "level": "critical", "detail": "HTTP 429"},
        ]
    }
    summary = repair_engine.run_mechanic(report, db=db)
    # No OPENROUTER_BACKUP_KEY configured → escalate
    assert any(r["detail"] == "escalated" for r in summary["repairs"])


def test_escalation_create_resolve(db):
    """Escalation manager should create and resolve escalate items."""
    eid = escalation_manager.create_escalation(db, "test", "Test escalation", "details")
    open_items = escalation_manager.open_escalations(db)
    assert any(i["id"] == eid for i in open_items)

    escalation_manager.resolve_escalation(db, eid)
    open_items = escalation_manager.open_escalations(db)
    assert not any(i["id"] == eid for i in open_items)