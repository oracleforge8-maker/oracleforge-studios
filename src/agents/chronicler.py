"""The Chronicler — archival, financial tracking, and weekly reports.

Responsibilities:
1. **Daily JSON archive** — dump all key tables to ``data/archive/YYYY/MM/DD/``
   as JSON/JSONL files so the entire history is preserved independently of SQLite.
2. **Weekly report** — generate matplotlib summary charts covering:
   trend motion, post counts, and financial health.
3. **Financial snapshot** — aggregate costs/revenues from ``financial_records``
   and write a JSON summary into the day's archive folder.

CLI:
    python main.py --run-chronicle            # archive mode
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from .. import config
from ..logger import get_logger
from ..utils import date_path

log = get_logger("chronicler")

#: Report output directory
REPORTS_DIR = config.PROJECT_ROOT / "data" / "reports"


def archive_root() -> Path:
    """Resolve and create the archive root directory.

    Returns:
        Path to ``data/archive`` (created if missing).
    """
    raw = config.env("ARCHIVE_PATH", "data/archive")
    path = Path(raw)
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Any) -> None:
    """Write data as pretty JSON.

    Args:
        path: Destination path.
        data: Serializable object.
    """
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Archival
# ---------------------------------------------------------------------------

def collect_snapshot(db: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Collect all table rows into a single snapshot dict.

    Args:
        db: Database instance.

    Returns:
        Dict mapping table name -> list of row dicts. Newest first.
    """
    return {
        "trends": db.query("SELECT * FROM trends ORDER BY captured_at DESC"),
        "posts": db.query("SELECT * FROM posts ORDER BY created_at DESC"),
        "subscribers": db.query("SELECT * FROM subscribers ORDER BY joined_at DESC"),
        "financial_records": db.query("SELECT * FROM financial_records ORDER BY recorded_at DESC"),
        "celebrity_posts": db.query("SELECT * FROM celebrity_posts ORDER BY captured_at DESC"),
        "replies": db.query("SELECT * FROM replies ORDER BY created_at DESC"),
    }


def archive_daily(db: Any) -> Dict[str, Any]:
    """Write today's full archive snapshot to disk.

    Args:
        db: Database instance.

    Returns:
        Dict describing what was archived (snapshot path + counts).
    """
    root = archive_root()
    today = date_path(root)

    snapshot = collect_snapshot(db)

    # One combined snapshot file + per-table files for convenience
    combined_path = today / "snapshot.json"
    _write_json(combined_path, snapshot)
    log.info("Archive written: %s", combined_path)

    counts = {name: len(rows) for name, rows in snapshot.items()}
    for name, rows in snapshot.items():
        table_path = today / f"{name}.json"
        _write_json(table_path, rows)
        log.debug("Archived %s: %d rows", name, len(rows))

    return {"path": str(combined_path), "counts": counts}


def financial_snapshot(db: Any) -> Dict[str, float]:
    """Produce and persist a financial summary JSON for today.

    Args:
        db: Database instance.

    Returns:
        Dict financial summary (cost/revenue/expense/net).
    """
    summary = db.financial_summary()
    root = archive_root()
    today = date_path(root)
    path = today / "financials.json"
    _write_json(path, {"generated_at": _now(), **summary})
    log.info("Financial snapshot written: %s", path)
    return summary


# ---------------------------------------------------------------------------
# Weekly report
# ---------------------------------------------------------------------------

def generate_weekly_report(db: Any) -> Path:
    """Generate a weekly report PNG with matplotlib charts.

    Charts:
    1. Top movers this week (avg price change by symbol)
    2. Posts per platform (bar chart)
    3. Financial summary (cost vs revenue bar)

    Args:
        db: Database instance.

    Returns:
        Path to the generated PNG report.
    """
    import matplotlib
    matplotlib.use("Agg")  # headless renderer
    import matplotlib.pyplot as plt

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    since = datetime.now(timezone.utc) - timedelta(days=7)
    since_str = since.isoformat(timespec="seconds")

    # 1) Top movers from the last 7 days
    trend_rows = db.query(
        "SELECT token_symbol, AVG(price_change_pct) AS avg_chg "
        "FROM trends WHERE captured_at >= ? AND price_change_pct IS NOT NULL "
        "GROUP BY token_symbol ORDER BY avg_chg DESC LIMIT 8",
        (since_str,),
    )

    # 2) Posts by platform (last 7 days)
    post_rows = db.query(
        "SELECT platform, COUNT(*) AS n FROM posts "
        "WHERE created_at >= ? GROUP BY platform", (since_str,),
    )

    # 3) Financials
    fin = db.financial_summary()

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("OracleForge Weekly Report", fontsize=16, fontweight="bold")

    # Chart 1: Top movers
    ax = axes[0]
    if trend_rows:
        symbols = [r["token_symbol"] for r in trend_rows]
        values = [float(r["avg_chg"]) for r in trend_rows]
        colors = ["#00FF88" if v >= 0 else "#FF5555" for v in values]
        ax.bar(symbols, values, color=colors)
        ax.set_title("Top Movers (7d avg %)")
        ax.set_ylabel("% change")
        ax.tick_params(axis="x", rotation=45)
    else:
        ax.text(0.5, 0.5, "No trend data", ha="center", va="center")
        ax.set_title("Top Movers (7d avg %)")

    # Chart 2: Posts per platform
    ax = axes[1]
    if post_rows:
        platforms = [r["platform"] for r in post_rows]
        counts = [r["n"] for r in post_rows]
        ax.bar(platforms, counts, color="#2D1B69")
        ax.set_title("Posts by Platform (7d)")
        ax.set_ylabel("count")
    else:
        ax.text(0.5, 0.5, "No posts", ha="center", va="center")
        ax.set_title("Posts by Platform (7d)")

    # Chart 3: Financials
    ax = axes[2]
    labels = ["Cost", "Revenue", "Expense"]
    values = [fin["cost"], fin["revenue"], fin["expense"]]
    ax.bar(labels, values, color=["#FF5555", "#00FF88", "#FFAA00"])
    ax.set_title(f"Financials (net ${fin['net']:,.4f})")

    fig.tight_layout(rect=[0, 0, 1, 0.94])

    filename = f"weekly_report_{datetime.now():%Y%m%d_%H%M}.png"
    out_path = REPORTS_DIR / filename
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    log.info("Weekly report generated: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_chronicle(mode: str = "archive", db: Any = None) -> Any:
    """Run a Chronicler task.

    Args:
        mode: archive | report.
        db: Optional Database instance.

    Returns:
        Task-dependent result (snapshot dict or report path).
    """
    if db is None:
        from ..database import get_db
        db = get_db()

    if mode == "archive":
        result = archive_daily(db)
        fin = financial_snapshot(db)
        result["financials"] = fin
        print(f"📦 Archived: trends={result['counts'].get('trends', 0)}, "
              f"posts={result['counts'].get('posts', 0)}, "
              f"subscribers={result['counts'].get('subscribers', 0)}")
        print(f"💰 Financials: {fin}")
        return result

    if mode == "report":
        path = generate_weekly_report(db)
        print(f"📊 Weekly report generated: {path}")
        return path

    log.error("Unknown chronicle mode: %s", mode)
    return None


def _now() -> str:
    """Current UTC ISO timestamp for labels."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")