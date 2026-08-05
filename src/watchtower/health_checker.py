"""The Watchtower — health checker.

Runs a battery of checks and returns a structured health report:

1. API connectivity (OpenRouter, OpenAI, Twitter, Stripe)
2. Database integrity (SQLite tables + archive files)
3. Social posting success (last N posts per platform)
4. Website uptime
5. Log scanning for recent errors

Each check is isolated — a failure in one never stops the others. Results are
color-coded: green (ok), yellow (warning), red (critical).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .. import config
from ..logger import get_logger
from ..utils import utcnow

log = get_logger("watchtower")

#: Severity levels (higher = worse)
SEVERITY = {"ok": 0, "warning": 1, "critical": 2}


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_health_config() -> Dict[str, Any]:
    """Load health_config.yaml.

    Returns:
        Health config dict.
    """
    return config.load_yaml("health_config.yaml")


def _severity_color(level: str) -> str:
    """Map a severity level to a color.

    Args:
        level: ok | warning | critical.

    Returns:
        Color hex string.
    """
    return {"ok": "#00FF88", "warning": "#FFAA00", "critical": "#FF5555"}.get(level, "#C0C0C0")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def check_api_connectivity(session: aiohttp.ClientSession,
                                 cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check connectivity to each configured API.

    Args:
        session: aiohttp session.
        cfg: Health config.

    Returns:
        List of check result dicts.
    """
    results: List[Dict[str, Any]] = []
    timeout = aiohttp.ClientTimeout(total=cfg.get("check_timeout_seconds", 10))

    for api in cfg.get("api_checks", []):
        name = api["name"]
        key_env = api.get("requires_key", "")
        # If the key isn't configured, mark as "skipped" (not an error)
        if key_env and not config.env(key_env):
            results.append({
                "name": f"api:{name}",
                "status": "ok",
                "level": "ok",
                "detail": f"not configured ({key_env} unset) — skipped",
            })
            continue

        try:
            async with session.get(api["url"], timeout=timeout) as resp:
                ok = resp.status < 500
                results.append({
                    "name": f"api:{name}",
                    "status": "ok" if ok else "critical",
                    "level": "ok" if ok else "critical",
                    "detail": f"HTTP {resp.status}",
                })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "name": f"api:{name}",
                "status": "critical",
                "level": "critical",
                "detail": f"unreachable: {exc}",
            })

    return results


def check_database(db: Any, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify database integrity.

    Args:
        db: Database instance.
        cfg: Health config.

    Returns:
        List of check result dicts.
    """
    results: List[Dict[str, Any]] = []
    required = cfg.get("database", {}).get("required_tables", [])

    try:
        tables = {row["name"] for row in db.query(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        missing = [t for t in required if t not in tables]
        if missing:
            results.append({
                "name": "db:tables",
                "status": "critical",
                "level": "critical",
                "detail": f"missing tables: {missing}",
            })
        else:
            results.append({
                "name": "db:tables",
                "status": "ok",
                "level": "ok",
                "detail": f"all {len(required)} tables present",
            })
    except Exception as exc:  # noqa: BLE001
        results.append({
            "name": "db:tables",
            "status": "critical",
            "level": "critical",
            "detail": f"db error: {exc}",
        })

    # Archive files
    archive_root = config.PROJECT_ROOT / config.env("ARCHIVE_PATH", "data/archive")
    if archive_root.exists():
        results.append({
            "name": "db:archive",
            "status": "ok",
            "level": "ok",
            "detail": f"archive exists ({archive_root})",
        })
    else:
        results.append({
            "name": "db:archive",
            "status": "warning",
            "level": "warning",
            "detail": "archive directory missing",
        })

    return results


def check_social_posts(db: Any, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify recent social posts succeeded.

    Args:
        db: Database instance.
        cfg: Health config.

    Returns:
        List of check result dicts.
    """
    results: List[Dict[str, Any]] = []
    platforms = cfg.get("social", {}).get("platforms", ["twitter", "discord", "linkedin"])
    check_n = cfg.get("social", {}).get("check_last_posts", 3)

    for platform in platforms:
        posts = db.latest_posts(limit=check_n, platform=platform)
        if not posts:
            results.append({
                "name": f"social:{platform}",
                "status": "warning",
                "level": "warning",
                "detail": "no posts found",
            })
            continue
        failed = [p for p in posts if p.get("status") == "failed"]
        if failed:
            results.append({
                "name": f"social:{platform}",
                "status": "warning",
                "level": "warning",
                "detail": f"{len(failed)}/{len(posts)} recent posts failed",
            })
        else:
            results.append({
                "name": f"social:{platform}",
                "status": "ok",
                "level": "ok",
                "detail": f"last {len(posts)} posts ok",
            })

    return results


async def check_website(session: aiohttp.ClientSession,
                        cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check website uptime.

    Args:
        session: aiohttp session.
        cfg: Health config.

    Returns:
        List of check result dicts.
    """
    url = cfg.get("website", {}).get("url", "http://localhost:5000")
    expected = cfg.get("website", {}).get("expected_status", 200)
    timeout = aiohttp.ClientTimeout(total=cfg.get("check_timeout_seconds", 10))

    try:
        async with session.get(url, timeout=timeout) as resp:
            ok = resp.status == expected
            results = [{
                "name": "website",
                "status": "ok" if ok else "critical",
                "level": "ok" if ok else "critical",
                "detail": f"HTTP {resp.status} (expected {expected})",
            }]
    except Exception as exc:  # noqa: BLE001
        results = [{
            "name": "website",
            "status": "critical",
            "level": "critical",
            "detail": f"unreachable: {exc}",
        }]
    return results


def check_logs(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan recent log lines for errors.

    Args:
        cfg: Health config.

    Returns:
        List of check result dicts.
    """
    log_dir = config.PROJECT_ROOT / config.env("LOG_PATH", "logs")
    keywords = cfg.get("logs", {}).get("error_keywords", ["ERROR", "Traceback"])
    scan_lines = cfg.get("logs", {}).get("scan_recent_lines", 200)

    if not log_dir.exists():
        return [{
            "name": "logs",
            "status": "warning",
            "level": "warning",
            "detail": "log directory missing",
        }]

    # Find today's log file
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = log_dir / f"oracleforge_{today}.log"
    if not log_file.exists():
        return [{
            "name": "logs",
            "status": "ok",
            "level": "ok",
            "detail": "no log file for today yet",
        }]

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-scan_lines:]
        errors = [ln for ln in lines if any(kw in ln for kw in keywords)]
        if errors:
            return [{
                "name": "logs",
                "status": "warning",
                "level": "warning",
                "detail": f"{len(errors)} error lines in last {scan_lines}",
            }]
        return [{
            "name": "logs",
            "status": "ok",
            "level": "ok",
            "detail": f"no errors in last {scan_lines} lines",
        }]
    except Exception as exc:  # noqa: BLE001
        return [{
            "name": "logs",
            "status": "warning",
            "level": "warning",
            "detail": f"log scan failed: {exc}",
        }]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_health_check(db: Any = None) -> Dict[str, Any]:
    """Run all health checks and produce a report.

    Args:
        db: Optional Database instance.

    Returns:
        Structured health report dict.
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    cfg = _load_health_config()
    log.info("🔍 Watchtower health check starting")

    async with aiohttp.ClientSession() as session:
        api_results = await check_api_connectivity(session, cfg)
        website_results = await check_website(session, cfg)

    db_results = check_database(db, cfg)
    social_results = check_social_posts(db, cfg)
    log_results = check_logs(cfg)

    all_checks = api_results + db_results + social_results + website_results + log_results

    # Aggregate severity
    worst = max((SEVERITY.get(c["level"], 0) for c in all_checks), default=0)
    overall = {0: "ok", 1: "warning", 2: "critical"}[worst]

    report = {
        "generated_at": _now(),
        "overall": overall,
        "color": _severity_color(overall),
        "checks": all_checks,
        "summary": {
            "total": len(all_checks),
            "ok": sum(1 for c in all_checks if c["level"] == "ok"),
            "warning": sum(1 for c in all_checks if c["level"] == "warning"),
            "critical": sum(1 for c in all_checks if c["level"] == "critical"),
        },
    }

    log.info("Watchtower report: %s (%d ok, %d warn, %d crit)",
             overall, report["summary"]["ok"],
             report["summary"]["warning"], report["summary"]["critical"])
    return report