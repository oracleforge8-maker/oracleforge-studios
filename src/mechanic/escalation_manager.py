"""The Mechanic — escalation manager.

When a repair fails or requires human action (e.g. no backup API key, or a
service needs manual intervention), the escalation manager:

1. Records the escalation in the database (``escalations`` table).
2. Writes an escalation alert file that the Observatory dashboard surfaces.
3. Optionally sends an email alert if SMTP is configured.

The dashboard shows pending escalations prominently so a human can act.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import config
from ..logger import get_logger

log = get_logger("escalation_manager")


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_escalation_table(db: Any) -> None:
    """Create the escalations table if it does not exist.

    Args:
        db: Database instance.
    """
    db.execute(
        """CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,          -- e.g. mechanic, watchtower
            title TEXT NOT NULL,
            detail TEXT,
            status TEXT NOT NULL DEFAULT 'open',  -- open / resolved
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )"""
    )


def create_escalation(db: Any, source: str, title: str, detail: str = "") -> int:
    """Record a new escalation.

    Args:
        db: Database instance.
        source: Where the escalation came from.
        title: Short human-readable title.
        detail: Longer description.

    Returns:
        New escalation row id.
    """
    ensure_escalation_table(db)
    row_id = db.execute(
        "INSERT INTO escalations (source, title, detail, status, created_at) "
        "VALUES (?, ?, ?, 'open', ?)",
        (source, title, detail, _now()),
    ).lastrowid
    log.warning("🚨 Escalation created [%s]: %s", source, title)
    _write_alert_file(db)
    return row_id


def resolve_escalation(db: Any, escalation_id: int) -> None:
    """Mark an escalation as resolved.

    Args:
        db: Database instance.
        escalation_id: Escalation row id.
    """
    ensure_escalation_table(db)
    db.execute(
        "UPDATE escalations SET status='resolved', resolved_at=? WHERE id=?",
        (_now(), escalation_id),
    )
    log.info("Escalation %d resolved", escalation_id)
    _write_alert_file(db)


def open_escalations(db: Any, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch open escalations.

    Args:
        db: Database instance.
        limit: Max rows.

    Returns:
        List of open escalation dicts (newest first).
    """
    ensure_escalation_table(db)
    return db.query(
        "SELECT * FROM escalations WHERE status='open' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def all_escalations(db: Any, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch all escalations (open + resolved).

    Args:
        db: Database instance.
        limit: Max rows.

    Returns:
        List of escalation dicts (newest first).
    """
    ensure_escalation_table(db)
    return db.query(
        "SELECT * FROM escalations ORDER BY created_at DESC LIMIT ?", (limit,)
    )


def _write_alert_file(db: Any) -> None:
    """Write a JSON alert file for the dashboard to surface.

    Args:
        db: Database instance.
    """
    open_items = open_escalations(db, limit=50)
    alert_path = config.PROJECT_ROOT / "data" / "escalations.json"
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    alert_path.write_text(
        json.dumps({"generated_at": _now(), "open": open_items}, indent=2, default=str),
        encoding="utf-8",
    )


def send_email_alert(title: str, detail: str) -> bool:
    """Send an email alert if SMTP is configured.

    Args:
        title: Alert subject.
        detail: Alert body.

    Returns:
        True if sent, False if SMTP not configured or send failed.
    """
    smtp_host = config.env("SMTP_HOST")
    if not smtp_host:
        log.info("SMTP not configured — skipping email alert")
        return False

    try:
        import smtplib
        from email.mime.text import MIMEText

        sender = config.env("SMTP_FROM", "alerts@oracleforge.ai")
        recipient = config.env("ALERT_EMAIL", "")
        if not recipient:
            log.info("ALERT_EMAIL not set — skipping email alert")
            return False

        msg = MIMEText(detail)
        msg["Subject"] = f"[OracleForge] {title}"
        msg["From"] = sender
        msg["To"] = recipient

        port = config.env_int("SMTP_PORT", 587)
        with smtplib.SMTP(smtp_host, port, timeout=15) as server:
            server.starttls()
            server.login(config.env("SMTP_USER", ""), config.env("SMTP_PASSWORD", ""))
            server.send_message(msg)
        log.info("Email alert sent to %s", recipient)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Email alert failed: %s", exc)
        return False