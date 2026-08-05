"""Logging setup for OracleForge.

Creates a ``logs/`` directory at the project root with daily log files
named ``oracleforge_YYYYMMDD.log``. Each module gets its own logger via
:func:`get_logger`, which inherits from the root "OracleForge" logger.

The logger is resilient — if the filesystem fails, it falls back to
console-only output so the system never crashes on a logging error.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

from . import config

#: Default log format — includes timestamp, level, module, message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _log_dir() -> Path:
    """Resolve and create the log directory.

    Uses ``LOG_PATH`` from the environment (relative to project root).

    Returns:
        Path to the log directory (created if missing).
    """
    log_path = config.env("LOG_PATH", "logs")
    path = Path(log_path)
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure() -> None:
    """Configure the root OracleForge logger once.

    Adds a rotating file handler (daily) and a console handler.
    Safe to call multiple times — reconfiguration is idempotent.
    """
    root = logging.getLogger("OracleForge")
    if getattr(root, "_configured", False):
        return
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- File handler: daily rotation ---
    try:
        log_dir = _log_dir()
        filename = f"oracleforge_{datetime.now():%Y%m%d}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / filename,
            maxBytes=5 * 1024 * 1024,  # 5 MB per file
            backupCount=7,             # keep a week of history
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
    except (OSError, PermissionError) as exc:
        # Non-fatal — console logging still works
        print(f"[logger] Could not create file handler: {exc}", file=sys.stderr)

    # --- Console handler ---
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    root.addHandler(console)

    root._configured = True  # type: ignore[attr-defined]
    root.info("OracleForge logger initialized")


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the OracleForge root.

    Args:
        name: Module/component name (e.g. "scout", "brain").

    Returns:
        Configured child logger.
    """
    _configure()
    return logging.getLogger(f"OracleForge.{name}")