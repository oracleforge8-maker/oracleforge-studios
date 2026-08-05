"""Shared utilities for OracleForge agents.

Provides:
- :func:`retry` — async retry with exponential backoff + jitter for flaky APIs
- :func:`safe_json` — tolerant JSON parsing (extracts JSON from AI output)
- :func:`utcnow`, :func:`date_path` — timestamp helpers for archival
- :func:`log_financial` — records API costs/expenses to financial_records
- :func:`slugify` — URL/file-safe strings
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def utcnow() -> str:
    """Return current UTC time as ISO-8601 string.

    Returns:
        e.g. "2026-07-31T21:15:00.000Z"
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def date_path(base: Path, when: Optional[datetime] = None) -> Path:
    """Build a ``YYYY/MM/DD`` archive path under a base directory.

    Args:
        base: Root directory for archives.
        when: Optional datetime (defaults to now UTC).

    Returns:
        Path like ``base/2026/07/31`` (already created).
    """
    dt = when or datetime.now(timezone.utc)
    path = base / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def safe_json(text: str) -> Optional[Any]:
    """Parse JSON from possibly noisy LLM output.

    Tries strict parse first; if that fails, extracts the first
    ``{...}`` or ``[...]`` block and tries again.

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Parsed object or None if nothing parseable was found.
    """
    if not text:
        return None
    # First try strict
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to trim markdown fences
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Extract first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Extract first [...] block
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def to_json_lines(items: List[Dict[str, Any]]) -> str:
    """Serialize a list of dicts to one-JSON-object-per-line.

    Args:
        items: List of dicts.

    Returns:
        JSONL string.
    """
    return "\n".join(json.dumps(item, default=str) for item in items)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Convert arbitrary text into a URL/file-safe slug.

    Args:
        text: Input text.

    Returns:
        Lowercase hyphenated slug.
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


# ---------------------------------------------------------------------------
# Async retry
# ---------------------------------------------------------------------------


async def retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
    logger: Optional[Any] = None,
) -> T:
    """Run an async callable with exponential backoff retries.

    Args:
        coro_factory: Zero-arg callable returning a coroutine.
        attempts: Maximum number of tries (including the first).
        base_delay: Initial delay in seconds.
        max_delay: Ceiling for backoff in seconds.
        jitter: Random multiplier range (0..jitter) added to each delay.
        logger: Optional logger for failure messages.

    Returns:
        The awaited result of the callable.

    Raises:
        The last exception after all attempts are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 — retry any API failure
            last_exc = exc
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay = delay * (1 + random.random() * jitter)
            if logger:
                logger.warning(
                    "Attempt %d/%d failed (%s). Retrying in %.1fs...",
                    attempt, attempts, exc, delay,
                )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


def retry_sync(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
    logger: Optional[Any] = None,
) -> T:
    """Sync version of :func:`retry` for non-async callers.

    Args:
        func: Zero-arg callable.
        attempts: Maximum tries.
        base_delay: Initial delay.
        max_delay: Backoff ceiling.
        jitter: Random jitter multiplier.
        logger: Optional logger.

    Returns:
        The callable's result.

    Raises:
        The last exception after all attempts.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay = delay * (1 + random.random() * jitter)
            if logger:
                logger.warning(
                    "Attempt %d/%d failed (%s). Retrying in %.1fs...",
                    attempt, attempts, exc, delay,
                )
            time.sleep(delay)  # local import kept at call site
    assert last_exc is not None
    raise last_exc
