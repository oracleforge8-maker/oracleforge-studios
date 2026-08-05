"""The Watchtower — reporter.

Persists health check history to disk (JSON) and provides helpers to build
structured, color-coded reports for the Observatory dashboard.

History is stored at ``data/health/history.json`` (non-secret — health status
only, never credentials).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .. import config
from ..logger import get_logger

log = get_logger("watchtower_reporter")

#: Max history entries to keep
MAX_HISTORY = 500


def _history_path() -> Path:
    """Resolve the health history file path.

    Returns:
        Path to ``data/health/history.json``.
    """
    path = config.PROJECT_ROOT / "data" / "health" / "history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _latest_path() -> Path:
    """Resolve the full latest-report file path.

    Returns:
        Path to ``data/health/latest.json``.
    """
    path = config.PROJECT_ROOT / "data" / "health" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_report(report: Dict[str, Any]) -> Path:
    """Append a health report to the history file.

    Also persists the FULL report (including checks) to ``latest.json`` so
    The Mechanic can act on the detailed check results.

    Args:
        report: Health report dict from ``run_health_check``.

    Returns:
        Path to the history file.
    """
    path = _history_path()
    history: List[Dict[str, Any]] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []

    # Keep only the summary + timestamp for history (compact)
    history.append({
        "generated_at": report.get("generated_at", _now()),
        "overall": report.get("overall", "unknown"),
        "summary": report.get("summary", {}),
    })
    history = history[-MAX_HISTORY:]

    path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    # Persist the full report (with checks) for The Mechanic
    _latest_path().write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    log.info("Health report saved to history (%d entries)", len(history))
    return path


def load_latest() -> Dict[str, Any]:
    """Load the full latest health report (with checks).

    Returns:
        The full report dict, or an empty placeholder if none exists.
    """
    path = _latest_path()
    if not path.exists():
        return {"generated_at": "", "overall": "unknown", "summary": {}, "checks": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"generated_at": "", "overall": "unknown", "summary": {}, "checks": []}


def load_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Load recent health history.

    Args:
        limit: Max entries to return (newest first).

    Returns:
        List of history entries.
    """
    path = _history_path()
    if not path.exists():
        return []
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return history[-limit:][::-1]


def build_dashboard_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a dashboard-friendly report view.

    Args:
        report: Full health report.

    Returns:
        Dict with overall status, color, summary, and checks.
    """
    return {
        "generated_at": report.get("generated_at", _now()),
        "overall": report.get("overall", "unknown"),
        "color": report.get("color", "#C0C0C0"),
        "summary": report.get("summary", {}),
        "checks": report.get("checks", []),
    }