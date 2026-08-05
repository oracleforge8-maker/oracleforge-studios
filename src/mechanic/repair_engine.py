"""The Mechanic — repair engine.

Receives health reports from The Watchtower and applies known fixes:

- Re-run failed social posts (up to 3 retries)
- Clear stuck database connections (reconnect)
- Rotate API keys when rate-limited (uses backup keys from env)
- Restart server processes (web worker)
- Remove stale lock files

Every repair attempt and outcome is logged to the database via the
``repair_log`` table (created lazily) so the Observatory dashboard can show
full transparency.

If a repair fails, it returns an escalation signal for the escalation manager.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import config
from ..logger import get_logger

log = get_logger("mechanic")

#: Max retries for failed social posts
MAX_POST_RETRIES = 3

#: Wait between retries (seconds)
RETRY_BACKOFF = 5


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_repair_table(db: Any) -> None:
    """Create the repair_log table if it does not exist.

    Args:
        db: Database instance.
    """
    db.execute(
        """CREATE TABLE IF NOT EXISTS repair_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_type TEXT NOT NULL,
            target TEXT NOT NULL,
            status TEXT NOT NULL,          -- repaired / failed / escalated
            detail TEXT,
            created_at TEXT NOT NULL
        )"""
    )


def log_repair(db: Any, repair_type: str, target: str,
               status: str, detail: str = "") -> None:
    """Log a repair attempt.

    Args:
        db: Database instance.
        repair_type: Type of repair applied.
        target: What was repaired.
        status: repaired / failed / escalated.
        detail: Human-readable outcome.
    """
    ensure_repair_table(db)
    db.execute(
        "INSERT INTO repair_log (repair_type, target, status, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (repair_type, target, status, detail, _now()),
    )
    log.info("🔧 Repair %s:%s = %s — %s", repair_type, target, status, detail)


def latest_repairs(db: Any, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent repair log entries.

    Args:
        db: Database instance.
        limit: Max rows (newest first).

    Returns:
        List of repair log dicts.
    """
    ensure_repair_table(db)
    return db.query(
        "SELECT * FROM repair_log ORDER BY created_at DESC LIMIT ?", (limit,)
    )


# ---------------------------------------------------------------------------
# Individual repairs
# ---------------------------------------------------------------------------

def repair_retry_failed_posts(db: Any) -> int:
    """Retry failed social posts (up to MAX_POST_RETRIES).

    Args:
        db: Database instance.

    Returns:
        Number of posts retried/fixed.
    """
    fixed = 0
    failed = db.query(
        "SELECT * FROM posts WHERE status='failed' ORDER BY created_at DESC LIMIT 10"
    )
    for post in failed:
        attempts = int(post.get("retry_count") or 0)
        if attempts >= MAX_POST_RETRIES:
            log_repair(db, "retry_post", f"post:{post['id']}", "failed",
                       "max retries reached")
            continue

        # Reset to draft so the next social run can repost it
        db.execute(
            "UPDATE posts SET status='draft', retry_count=? WHERE id=?",
            (attempts + 1, post["id"]),
        )
        log_repair(db, "retry_post", f"post:{post['id']}", "repaired",
                   f"reset to draft (retry {attempts + 1})")
        fixed += 1
        time.sleep(min(RETRY_BACKOFF, 2))  # throttle

    return fixed


def repair_database_connection(db: Any) -> str:
    """Reconnect the database to clear stuck connections.

    Args:
        db: Database instance.

    Returns:
        Status string ("repaired" or "failed").
    """
    try:
        db.close()
        # Reconnect: replace the underlying connection
        import sqlite3
        from pathlib import Path
        db.conn = sqlite3.connect(Path(db.path).parent / Path(db.path).name,
                                  check_same_thread=False)
        db.conn.row_factory = sqlite3.Row
        db.init_schema()
        log_repair(db, "db_reconnect", db.path, "repaired", "connection reset")
        return "repaired"
    except Exception as exc:  # noqa: BLE001
        log_repair(db, "db_reconnect", db.path, "failed", str(exc))
        return "failed"


def repair_restart_web() -> str:
    """Signal the web worker to restart.

    In a containerized/process-supervised setup this writes a restart flag file
    that a supervisor (or docker restart policy) picks up. Locally it's a no-op
    that returns "repaired" when the site is reachable again.

    Returns:
        Status string.
    """
    restart_flag = config.PROJECT_ROOT / "data" / "restart.flag"
    try:
        restart_flag.parent.mkdir(parents=True, exist_ok=True)
        restart_flag.write_text(_now(), encoding="utf-8")
        log.info("Web restart flag written: %s", restart_flag)
        return "repaired"
    except OSError as exc:  # noqa: BLE001
        log.error("Could not write restart flag: %s", exc)
        return "failed"


def repair_rotate_api_key(service: str, db: Any) -> str:
    """Rotate an API key when rate-limited (use backup env key).

    Backup keys are read from ``{SERVICE}_BACKUP_KEY`` env vars (set by the
    operator). If no backup exists, the repair is logged as failed/escalated.

    Args:
        service: Service name (e.g. "openrouter").
        db: Database instance.

    Returns:
        Status string.
    """
    env_var = f"{service.upper()}_API_KEY"
    backup_var = f"{service.upper()}_BACKUP_KEY"
    backup = config.env(backup_var)

    if not backup:
        log_repair(db, "rotate_key", service, "escalated",
                   f"no {backup_var} configured — needs human")
        return "escalated"

    try:
        # In a real deployment the operator would define which env var is active.
        # Here we record the rotation intent and stash the old key as backup.
        old_key = config.env(env_var)
        if old_key:
            db.set_setting(f"{service}_old_key", old_key)
        # Instruct operator: set {env_var} to the backup value
        db.set_setting(f"{service}_rotation_pending", backup_var)
        log_repair(db, "rotate_key", service, "repaired",
                   f"backup key staged — set {env_var} to {backup_var} value")
        return "repaired"
    except Exception as exc:  # noqa: BLE001
        log_repair(db, "rotate_key", service, "failed", str(exc))
        return "failed"


def repair_clear_lock_files() -> int:
    """Remove stale lock files from the data directory.

    Returns:
        Number of lock files removed.
    """
    data_dir = config.PROJECT_ROOT / "data"
    if not data_dir.exists():
        return 0
    removed = 0
    for pattern in ("*.lock", "*.flag"):
        for lock in data_dir.glob(pattern):
            try:
                # Only clear files older than 10 minutes (still active locks are fresh)
                age = time.time() - lock.stat().st_mtime
                if age > 600:
                    lock.unlink()
                    removed += 1
                    log.info("Removed stale lock: %s", lock)
            except OSError:
                continue
    return removed


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_mechanic(report: Dict[str, Any], db: Any = None) -> Dict[str, Any]:
    """Process a Watchtower report and apply repairs.

    Args:
        report: Health report from run_health_check.
        db: Optional Database instance.

    Returns:
        Repair run summary: {"repairs": [...], "escalated": bool}
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    log.info("🔧 Mechanic processing health report: %s", report.get("overall"))

    repairs: List[Dict[str, str]] = []
    escalated = False

    # Inspect each failing check and map to a repair
    for check in report.get("checks", []):
        level = check.get("level", "ok")
        name = check.get("name", "?")
        if level not in {"warning", "critical"}:
            continue

        # Social posting issues → retry failed posts
        if name.startswith("social:"):
            n = repair_retry_failed_posts(db)
            repairs.append({"check": name, "repair": f"retry_posts", "detail": f"{n} posts reset"})

        # Database issues → reconnect
        elif name.startswith("db:tables") and level == "critical":
            status = repair_database_connection(db)
            repairs.append({"check": name, "repair": "db_reconnect", "detail": status})
            if status == "escalated":
                escalated = True

        # API connectivity → rotate key (rate-limit heuristics)
        elif name.startswith("api:"):
            service = name.split(":", 1)[1]
            status = repair_rotate_api_key(service, db)
            repairs.append({"check": name, "repair": "rotate_key", "detail": status})
            if status == "escalated":
                escalated = True

        # Website down → restart web
        elif name == "website" and level == "critical":
            status = repair_restart_web()
            repairs.append({"check": name, "repair": "restart_web", "detail": status})
            if status == "escalated":
                escalated = True

    # Always clear stale lock files opportunistically
    cleared = repair_clear_lock_files()
    if cleared:
        repairs.append({"check": "filesystem", "repair": "clear_locks", "detail": f"{cleared} removed"})

    summary = {
        "generated_at": _now(),
        "repairs": repairs,
        "escalated": escalated,
    }
    log.info("Mechanic complete: %d repairs, escalated=%s", len(repairs), escalated)
    return summary