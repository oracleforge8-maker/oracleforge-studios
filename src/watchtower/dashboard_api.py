"""The Watchtower — dashboard API.

Exposes health data to the Observatory dashboard via a lightweight JSON API.
This is consumed by the dashboard server (``src/dashboard/server.py``).

Endpoints (mounted by the dashboard):
    GET  /api/health/latest   — most recent health report
    GET  /api/health/history  — recent health history
    GET  /api/health/run      — trigger a fresh health check (POST)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..logger import get_logger
from . import health_checker
from . import reporter

log = get_logger("watchtower_api")


def latest_report() -> Dict[str, Any]:
    """Return the most recent FULL health report (with checks).

    Returns:
        The full latest report (used by The Mechanic and dashboard), or an
        empty placeholder if none exists.
    """
    return reporter.load_latest()


def history(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent health history.

    Args:
        limit: Max entries.

    Returns:
        List of history entries (newest first).
    """
    return reporter.load_history(limit=limit)


async def run_check_and_save(db: Any = None) -> Dict[str, Any]:
    """Run a fresh health check and persist it.

    Args:
        db: Optional Database instance.

    Returns:
        The full health report.
    """
    report = await health_checker.run_health_check(db=db)
    reporter.save_report(report)
    return report