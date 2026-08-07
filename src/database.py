"""SQLite database layer — The Chronicler's core.

Manages the OracleForge database schema and provides safe, thread-safe
helper methods for all tables:

- ``trends``            — normalized scout data (tokens, prices, volumes)
- ``posts``             — all generated/planned social posts
- ``subscribers``       — waitlist signups with referral tracking
- ``financial_records`` — API costs, server expenses, earnings
- ``celebrity_posts``   — scraped celebrity posts for engagement
- ``replies``           — generated/sent replies to mentions & celebs

The database file lives at ``data/chronicler.db`` (from ``DATABASE_PATH``).
Uses ``check_same_thread=False`` + a lock so Flask workers and async
agents can share the connection safely.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .logger import get_logger

log = get_logger("database")


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS trends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,              -- e.g. twitter, pumpfun, cmc, reddit, dexscreener
    token_symbol    TEXT NOT NULL,
    token_name      TEXT,
    price           REAL,
    price_change_pct REAL,
    volume_24h      REAL,
    market_cap      REAL,
    rank            INTEGER,
    url             TEXT,
    raw_data        TEXT,                       -- JSON blob of the source payload
    captured_at     TEXT NOT NULL               -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_trends_captured_at ON trends(captured_at);
CREATE INDEX IF NOT EXISTS idx_trends_source ON trends(source);
CREATE INDEX IF NOT EXISTS idx_trends_symbol ON trends(token_symbol);

CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,              -- twitter, discord, linkedin, newsletter
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft, scheduled, posted, failed, mock
    post_type       TEXT,                       -- radar, celebrity, engagement, newsletter, b2b
    external_id     TEXT,                       -- platform post ID after posting
    scheduled_for   TEXT,
    posted_at       TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0, -- The Mechanic retry counter
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);

CREATE TABLE IF NOT EXISTS subscribers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT,
    referral_code   TEXT UNIQUE,
    referred_by     TEXT,                       -- referring subscriber's code
    referral_count  INTEGER NOT NULL DEFAULT 0,
    tier            TEXT NOT NULL DEFAULT 'free',  -- free, pro, forge
    pro_until       TEXT,                       -- ISO date if pro active
    joined_at       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);

CREATE TABLE IF NOT EXISTS financial_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type     TEXT NOT NULL,              -- cost, revenue, expense
    category        TEXT NOT NULL,              -- openrouter, openai, server, stripe, affiliate, other
    description     TEXT,
    amount          REAL NOT NULL,              -- positive USD; sign via record_type
    currency        TEXT NOT NULL DEFAULT 'USD',
    recorded_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_finance_recorded_at ON financial_records(recorded_at);

CREATE TABLE IF NOT EXISTS celebrity_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    celebrity_name  TEXT NOT NULL,
    post_text       TEXT NOT NULL,
    topic_hint      TEXT,
    url             TEXT,
    captured_at     TEXT NOT NULL,
    engaged         INTEGER NOT NULL DEFAULT 0   -- 0 = pending, 1 = commented
);

CREATE TABLE IF NOT EXISTS replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reply_to        TEXT NOT NULL,              -- reference to post/mention/celebrity
    target_type     TEXT NOT NULL,              -- mention, celebrity, post
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft, posted, failed, mock
    external_id     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

CREATE TABLE IF NOT EXISTS patrons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patreon_id      TEXT NOT NULL UNIQUE,       -- Patreon member ID
    email           TEXT,
    full_name       TEXT,
    tier            TEXT,                       -- Forge Supporter | Meme Master | Forge Master
    tier_level      INTEGER,                    -- 1 | 2 | 3
    status          TEXT NOT NULL DEFAULT 'active',  -- active | canceled | expired
    joined_at       TEXT,
    updated_at      TEXT,
    last_sync       TEXT                        -- last webhook/API sync time
);

CREATE INDEX IF NOT EXISTS idx_patrons_tier_level ON patrons(tier_level);
CREATE INDEX IF NOT EXISTS idx_patrons_status ON patrons(status);
"""


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

class Database:
    """Thread-safe SQLite wrapper for OracleForge."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize the database connection and schema.

        Args:
            db_path: Optional explicit path; defaults to ``DATABASE_PATH``
                     env var (or ``data/chronicler.db`` under project root).
        """
        self._lock = threading.Lock()
        if db_path is None:
            raw = config.env("DATABASE_PATH", "data/chronicler.db")
            db_path = Path(raw)
            if not db_path.is_absolute():
                db_path = config.PROJECT_ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.init_schema()

    # -- schema ------------------------------------------------------------

    def init_schema(self) -> None:
        """Create all tables and indexes if they do not exist."""
        with self._lock:
            self.conn.executescript(SCHEMA)
            self._migrate()
            self.conn.commit()

    def _migrate(self) -> None:
        """Apply lightweight migrations for pre-existing databases.

        Adds:
        - ``retry_count`` column to ``posts`` if missing (The Mechanic).
        - ``patrons`` table if missing (Patreon integration).
        """
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(posts)")}
        if "retry_count" not in cols:
            self.conn.execute(
                "ALTER TABLE posts ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
            )
            log.info("Migration: added posts.retry_count")
        # patrons table is created by SCHEMA's CREATE TABLE IF NOT EXISTS

    # -- generic helpers ----------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a write statement.

        Args:
            sql: SQL statement.
            params: Bound parameters.

        Returns:
            The cursor (for retrieving lastrowid).
        """
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run a SELECT and return list-of-dict rows.

        Args:
            sql: SQL statement.
            params: Bound parameters.

        Returns:
            List of dicts.
        """
        with self._lock:
            cur = self.conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Run a SELECT and return the first row (or None).

        Args:
            sql: SQL statement.
            params: Bound parameters.

        Returns:
            Single dict row or None.
        """
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- trends -------------------------------------------------------------

    def insert_trend(self, trend: Dict[str, Any]) -> int:
        """Insert a normalized trend record.

        Args:
            trend: Dict with keys matching the trends table columns.

        Returns:
            New row id.
        """
        sql = """
            INSERT INTO trends
                (source, token_symbol, token_name, price, price_change_pct,
                 volume_24h, market_cap, rank, url, raw_data, captured_at)
            VALUES
                (:source, :token_symbol, :token_name, :price, :price_change_pct,
                 :volume_24h, :market_cap, :rank, :url, :raw_data, :captured_at)
        """
        params = {
            "source": trend.get("source"),
            "token_symbol": trend.get("token_symbol") or trend.get("symbol"),
            "token_name": trend.get("token_name") or trend.get("name"),
            "price": trend.get("price"),
            "price_change_pct": trend.get("price_change_pct") or trend.get("change_pct"),
            "volume_24h": trend.get("volume_24h") or trend.get("volume"),
            "market_cap": trend.get("market_cap"),
            "rank": trend.get("rank"),
            "url": trend.get("url"),
            "raw_data": trend.get("raw_data"),
            "captured_at": trend.get("captured_at"),
        }
        return self.execute(sql, params).lastrowid

    def insert_trends(self, trends: List[Dict[str, Any]]) -> int:
        """Insert many trends in one transaction.

        Args:
            trends: List of trend dicts.

        Returns:
            Number inserted.
        """
        count = 0
        with self._lock:
            for trend in trends:
                # Inline the insert to avoid re-acquiring the (non-reentrant)
                # lock via insert_trend() — that would deadlock.
                sql = """
                    INSERT INTO trends
                        (source, token_symbol, token_name, price, price_change_pct,
                         volume_24h, market_cap, rank, url, raw_data, captured_at)
                    VALUES
                        (:source, :token_symbol, :token_name, :price, :price_change_pct,
                         :volume_24h, :market_cap, :rank, :url, :raw_data, :captured_at)
                """
                params = {
                    "source": trend.get("source"),
                    "token_symbol": trend.get("token_symbol") or trend.get("symbol"),
                    "token_name": trend.get("token_name") or trend.get("name"),
                    "price": trend.get("price"),
                    "price_change_pct": trend.get("price_change_pct") or trend.get("change_pct"),
                    "volume_24h": trend.get("volume_24h") or trend.get("volume"),
                    "market_cap": trend.get("market_cap"),
                    "rank": trend.get("rank"),
                    "url": trend.get("url"),
                    "raw_data": trend.get("raw_data"),
                    "captured_at": trend.get("captured_at"),
                }
                self.conn.execute(sql, params)
                count += 1
            self.conn.commit()
        return count

    def latest_trends(self, limit: int = 20, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch the most recent trends.

        Args:
            limit: Max rows.
            source: Optional source filter.

        Returns:
            List of trend dicts, newest first.
        """
        sql = "SELECT * FROM trends"
        params: tuple = ()
        if source:
            sql += " WHERE source = ?"
            params = (source,)
        sql += f" ORDER BY captured_at DESC LIMIT {int(limit)}"
        return self.query(sql, params)

    # -- posts --------------------------------------------------------------

    def create_post(self, platform: str, content: str, post_type: str = "radar",
                    status: str = "draft", scheduled_for: Optional[str] = None) -> int:
        """Create a social post record.

        Args:
            platform: twitter/discord/linkedin/newsletter.
            content: Post text.
            post_type: radar/celebrity/engagement/newsletter/b2b.
            status: draft/scheduled/posted/failed/mock.
            scheduled_for: Optional ISO datetime.

        Returns:
            New row id.
        """
        sql = """
            INSERT INTO posts (platform, content, status, post_type,
                               scheduled_for, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        return self.execute(
            sql,
            (platform, content, status, post_type, scheduled_for, _now()),
        ).lastrowid

    def mark_post_posted(self, post_id: int, external_id: str = "") -> None:
        """Update a post to posted status.

        Args:
            post_id: Row id.
            external_id: Platform post ID (optional).
        """
        self.execute(
            "UPDATE posts SET status='posted', external_id=?, posted_at=? WHERE id=?",
            (external_id, _now(), post_id),
        )

    def latest_posts(self, limit: int = 10, platform: Optional[str] = None,
                     status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch recent posts with optional filters.

        Args:
            limit: Max rows.
            platform: Optional platform filter.
            status: Optional status filter.

        Returns:
            List of post dicts, newest first.
        """
        sql = "SELECT * FROM posts"
        where: List[str] = []
        params: List[Any] = []
        if platform:
            where.append("platform = ?")
            params.append(platform)
        if status:
            where.append("status = ?")
            params.append(status)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
        return self.query(sql, tuple(params))

    # -- subscribers / waitlist ----------------------------------------------

    def add_subscriber(self, email: str, name: str = "",
                       referred_by: str = "") -> Dict[str, Any]:
        """Add a waitlist/subscriber (upsert by email).

        Args:
            email: Subscriber email.
            name: Optional display name.
            referred_by: Optional referral code of the referrer.

        Returns:
            The subscriber row dict.

        Raises:
            sqlite3.IntegrityError if email duplicate handling fails.
        """
        email = email.strip().lower()
        existing = self.query_one("SELECT * FROM subscribers WHERE email = ?", (email,))
        if existing:
            return existing
        code = _make_referral_code(email)
        now = _now()
        cur = self.execute(
            """INSERT INTO subscribers
               (email, name, referral_code, referred_by, joined_at)
               VALUES (?, ?, ?, ?, ?)""",
            (email, name, code, referred_by, now),
        )
        if referred_by:
            self._bump_referral_count(referred_by)
        return self.query_one("SELECT * FROM subscribers WHERE id = ?", (cur.lastrowid,)) or {}

    def _bump_referral_count(self, referral_code: str) -> None:
        """Increment a referrer's referral_count and upgrade if threshold met."""
        row = self.query_one(
            "SELECT id, referral_count FROM subscribers WHERE referral_code = ?",
            (referral_code,),
        )
        if not row:
            return
        new_count = row["referral_count"] + 1
        threshold = config.env_int("REFERRALS_FOR_FREE_PRO", 3)
        tier = "pro" if new_count >= threshold else "free"
        self.execute(
            "UPDATE subscribers SET referral_count = ?, tier = ? WHERE id = ?",
            (new_count, tier, row["id"]),
        )

    def subscriber_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Find a subscriber by referral code.

        Args:
            code: Referral code.

        Returns:
            Subscriber dict or None.
        """
        return self.query_one(
            "SELECT * FROM subscribers WHERE referral_code = ?", (code,)
        )

    def subscriber_count(self) -> int:
        """Count active subscribers.

        Returns:
            Total subscriber rows.
        """
        row = self.query_one("SELECT COUNT(*) AS n FROM subscribers")
        return int(row["n"]) if row else 0

    # -- financials -----------------------------------------------------------

    def add_financial(self, record_type: str, category: str, amount: float,
                      description: str = "") -> int:
        """Record a financial transaction.

        Args:
            record_type: cost/revenue/expense.
            category: openrouter/openai/server/stripe/affiliate/other.
            amount: Positive USD amount.
            description: Human-readable note.

        Returns:
            New row id.
        """
        sql = """
            INSERT INTO financial_records (record_type, category, description,
                                           amount, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(
            sql, (record_type, category, description, amount, _now())
        ).lastrowid

    def financial_summary(self) -> Dict[str, float]:
        """Aggregate costs, revenues, and expenses.

        Returns:
            Dict with keys: cost, revenue, expense, net.
        """
        rows = self.query("SELECT record_type, SUM(amount) AS total FROM financial_records GROUP BY record_type")
        summary = {"cost": 0.0, "revenue": 0.0, "expense": 0.0, "net": 0.0}
        for row in rows:
            summary[row["record_type"]] = float(row["total"] or 0.0)
        summary["net"] = summary["revenue"] - summary["cost"] - summary["expense"]
        return summary

    # -- celebrity posts -------------------------------------------------------

    def insert_celebrity_post(self, celebrity_name: str, post_text: str,
                              topic_hint: str = "", url: str = "") -> int:
        """Store a scraped celebrity post.

        Args:
            celebrity_name: Who posted.
            post_text: The post content.
            topic_hint: Detected occasion (birthday, party, ...).
            url: Optional link.

        Returns:
            New row id.
        """
        sql = """
            INSERT INTO celebrity_posts (celebrity_name, post_text, topic_hint, url, captured_at)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(
            sql, (celebrity_name, post_text, topic_hint, url, _now())
        ).lastrowid

    def unengaged_celebrity_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch celebrity posts not yet commented on.

        Args:
            limit: Max rows.

        Returns:
            List of celebrity post dicts.
        """
        return self.query(
            "SELECT * FROM celebrity_posts WHERE engaged = 0 ORDER BY captured_at DESC LIMIT ?",
            (limit,),
        )

    def mark_celebrity_engaged(self, post_id: int) -> None:
        """Mark a celebrity post as engaged/commented.

        Args:
            post_id: Row id.
        """
        self.execute("UPDATE celebrity_posts SET engaged = 1 WHERE id = ?", (post_id,))

    # -- replies ----------------------------------------------------------------

    def create_reply(self, reply_to: str, target_type: str, content: str,
                     status: str = "draft") -> int:
        """Record a generated reply.

        Args:
            reply_to: Reference to the target (post id, mention id, etc.).
            target_type: mention/celebrity/post.
            content: Reply text.
            status: draft/posted/failed/mock.

        Returns:
            New row id.
        """
        sql = """
            INSERT INTO replies (reply_to, target_type, content, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(sql, (reply_to, target_type, content, status, _now())).lastrowid

    def mark_reply_posted(self, reply_id: int, external_id: str = "") -> None:
        """Update a reply to posted.

        Args:
            reply_id: Row id.
            external_id: Platform reply ID (optional).
        """
        self.execute(
            "UPDATE replies SET status='posted', external_id=? WHERE id=?",
            (external_id, reply_id),
        )

    # -- settings ---------------------------------------------------------------

    def set_setting(self, key: str, value: str) -> None:
        """Store a key/value setting (upsert).

        Args:
            key: Setting key.
            value: Setting value.
        """
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_setting(self, key: str, default: str = "") -> str:
        """Read a setting value.

        Args:
            key: Setting key.
            default: Fallback if missing.

        Returns:
            Setting value or default.
        """
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    # -- patrons (Patreon integration) -----------------------------------------

    def upsert_patron(self, patron: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a patron by Patreon ID.

        Args:
            patron: Dict with keys: patreon_id, email, full_name, tier,
                    tier_level, status, joined_at.

        Returns:
            The stored patron row dict.
        """
        now = _now()
        patreon_id = patron.get("patreon_id", "")
        if not patreon_id:
            raise ValueError("patron requires patreon_id")

        existing = self.query_one(
            "SELECT id FROM patrons WHERE patreon_id = ?", (patreon_id,)
        )
        if existing:
            self.execute(
                """UPDATE patrons SET
                       email = ?, full_name = ?, tier = ?, tier_level = ?,
                       status = ?, joined_at = COALESCE(?, joined_at),
                       updated_at = ?, last_sync = ?
                   WHERE patreon_id = ?""",
                (
                    patron.get("email"),
                    patron.get("full_name"),
                    patron.get("tier"),
                    patron.get("tier_level"),
                    patron.get("status", "active"),
                    patron.get("joined_at"),
                    now,
                    now,
                    patreon_id,
                ),
            )
        else:
            self.execute(
                """INSERT INTO patrons
                   (patreon_id, email, full_name, tier, tier_level, status,
                    joined_at, updated_at, last_sync)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    patreon_id,
                    patron.get("email"),
                    patron.get("full_name"),
                    patron.get("tier"),
                    patron.get("tier_level"),
                    patron.get("status", "active"),
                    patron.get("joined_at"),
                    now,
                    now,
                ),
            )

        return self.query_one(
            "SELECT * FROM patrons WHERE patreon_id = ?", (patreon_id,)
        ) or {}

    def get_patron(self, patreon_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a patron by Patreon ID.

        Args:
            patreon_id: Patreon member ID.

        Returns:
            Patron row dict or None.
        """
        return self.query_one(
            "SELECT * FROM patrons WHERE patreon_id = ?", (patreon_id,)
        )

    def list_patrons(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch patrons, optionally filtered by status.

        Args:
            limit: Max rows.
            status: Optional status filter (active/canceled/expired).

        Returns:
            List of patron dicts, newest first by last_sync.
        """
        sql = "SELECT * FROM patrons"
        params: List[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += f" ORDER BY last_sync DESC LIMIT {int(limit)}"
        return self.query(sql, tuple(params))

    def delete_patron(self, patreon_id: str) -> bool:
        """Delete a patron by Patreon ID.

        Args:
            patreon_id: Patreon member ID.

        Returns:
            True if a row was deleted.
        """
        cur = self.execute(
            "DELETE FROM patrons WHERE patreon_id = ?", (patreon_id,)
        )
        return cur.rowcount > 0

    def patron_counts_by_tier(self) -> Dict[int, int]:
        """Count active patrons per tier level.

        Returns:
            Dict: tier_level -> count of active patrons.
        """
        rows = self.query(
            "SELECT tier_level, COUNT(*) AS n FROM patrons "
            "WHERE status = 'active' AND tier_level IS NOT NULL GROUP BY tier_level"
        )
        return {int(row["tier_level"]): int(row["n"]) for row in rows}

    def patron_total_active(self) -> int:
        """Count all active patrons.

        Returns:
            Total active patron rows.
        """
        row = self.query_one("SELECT COUNT(*) AS n FROM patrons WHERE status = 'active'")
        return int(row["n"]) if row else 0

    # -- misc -------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self.conn.close()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC ISO timestamp for DB defaults."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_referral_code(email: str) -> str:
    """Create a short, unique-ish referral code from an email."""
    import hashlib
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:10]
    return f"OF-{digest}"


def get_db() -> Database:
    """Return a shared module-level Database instance (lazy singleton).

    Returns:
        Database instance.
    """
    global _DB
    if _DB is None:
        _DB = Database()
    return _DB


#: Lazy singleton database instance
_DB: Optional[Database] = None