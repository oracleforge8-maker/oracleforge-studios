"""Built-in scheduler — lightweight cron runner for local dev.

Reads ``config/schedule.yaml`` and runs due jobs each minute. Suitable for
local development; for production prefer n8n workflows (``n8n/workflows.json``).

Each job is isolated — a failure in one never stops the others.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import config
from .logger import get_logger

log = get_logger("scheduler")

#: Job registry: name -> async callable
JOB_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register(name: str):
    """Decorator to register a job function.

    Args:
        name: Job name (matches schedule.yaml job keys).

    Returns:
        Decorator.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        JOB_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Cron parsing (minimal 5-field cron)
# ---------------------------------------------------------------------------

def _parse_field(field: str, lo: int, hi: int) -> set:
    """Parse a single cron field into a set of allowed values.

    Supports: *, */step, a-b, a,b,c.

    Args:
        field: Cron field string.
        lo: Minimum value.
        hi: Maximum value.

    Returns:
        Set of allowed integers.
    """
    values: set = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(lo, hi + 1))
        elif part.startswith("*/"):
            step = int(part[2:])
            values.update(range(lo, hi + 1, step))
        elif "-" in part:
            a, b = part.split("-")
            values.update(range(int(a), int(b) + 1))
        else:
            values.add(int(part))
    return values


class CronSchedule:
    """Minimal 5-field cron matcher (minute hour day month weekday)."""

    def __init__(self, expr: str) -> None:
        """Parse a cron expression.

        Args:
            expr: 5-field cron string.
        """
        fields = expr.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expr}")
        self.minutes = _parse_field(fields[0], 0, 59)
        self.hours = _parse_field(fields[1], 0, 23)
        self.days = _parse_field(fields[2], 1, 31)
        self.months = _parse_field(fields[3], 1, 12)
        self.weekdays = _parse_field(fields[4], 0, 6)

    def matches(self, dt: datetime) -> bool:
        """Check whether a datetime matches the schedule.

        Args:
            dt: Datetime to test.

        Returns:
            True if it matches.
        """
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days
            and dt.month in self.months
            and dt.weekday() in self.weekdays
        )


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

@register("run_scout")
async def job_scout() -> None:
    """Run The Scout scrapers."""
    from .agents.scout import run_scout
    await run_scout()


@register("run_brain")
async def job_brain() -> None:
    """Run The Brain analysis."""
    from .agents.brain import run_brain
    await run_brain(mode="analysis")


@register("run_chronicle")
async def job_chronicle() -> None:
    """Run The Chronicler archive."""
    from .agents.chronicler import run_chronicle
    await run_chronicle(mode="archive")


@register("run_social")
async def job_social() -> None:
    """Run The Radar posts (dry-run safe)."""
    from .agents.social_router import run_social
    await run_social(platform="twitter", dry_run=True, mode="radar_posts")


@register("run_forge")
async def job_forge() -> None:
    """Run The Forge brand image generation."""
    from .agents.forge import run_forge
    await run_forge(image_type="brand")


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

class Scheduler:
    """Runs due jobs from schedule.yaml every minute."""

    def __init__(self) -> None:
        """Load the schedule and prepare job tracking."""
        self.schedule = config.schedule()
        self._last_run: Dict[str, str] = {}

    def _due_jobs(self, now: datetime) -> List[Dict[str, Any]]:
        """Determine which jobs are due at the current time.

        Args:
            now: Current datetime.

        Returns:
            List of schedule blocks that are due.
        """
        due = []
        for name, block in self.schedule.items():
            cron = block.get("cron")
            if not cron:
                continue
            try:
                matcher = CronSchedule(cron)
            except ValueError as exc:
                log.warning("Bad cron for %s: %s", name, exc)
                continue
            if matcher.matches(now):
                due.append({"name": name, **block})
        return due

    async def _run_block(self, block: Dict[str, Any]) -> None:
        """Execute all jobs in a schedule block.

        Args:
            block: Schedule block dict with jobs list.
        """
        name = block.get("name", "unknown")
        jobs = block.get("jobs", [])
        log.info("Running schedule block: %s (%d jobs)", name, len(jobs))
        for job_name in jobs:
            fn = JOB_REGISTRY.get(job_name)
            if not fn:
                log.warning("Unknown job: %s", job_name)
                continue
            try:
                await fn()
                log.info("Job %s completed", job_name)
            except Exception as exc:  # noqa: BLE001 — isolation
                log.error("Job %s failed: %s", job_name, exc)

    def run_forever(self, interval: int = 60) -> None:
        """Run the scheduler loop forever.

        Args:
            interval: Poll interval in seconds (default 60).
        """
        log.info("Scheduler loop started (interval=%ds)", interval)
        while True:
            now = datetime.now(timezone.utc)
            due = self._due_jobs(now)
            for block in due:
                key = block["name"]
                minute_key = now.strftime("%Y%m%d%H%M")
                if self._last_run.get(key) == minute_key:
                    continue  # already ran this minute
                self._last_run[key] = minute_key
                asyncio.run(self._run_block(block))
            time.sleep(interval)