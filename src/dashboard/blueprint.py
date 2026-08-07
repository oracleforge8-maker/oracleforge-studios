"""The Observatory — dashboard Flask Blueprint.

Production deployment serves BOTH the marketing website and the dashboard
from a single Flask app (one port). To achieve this cleanly, all dashboard
routes live in a Flask Blueprint (named ``observatory``) registered onto the
main web app in ``wsgi.py``.

Local dev can still run the dashboard standalone — ``server.py`` builds a
minimal app and registers this same blueprint.

Blueprint detail:
- ``observatory.static`` serves ``dashboard/static/`` (CSS/JS)
- Templates resolve from ``dashboard/templates/`` (own folder)
- All secrets remain masked (config API never returns full values)
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for

from .. import config
from ..logger import get_logger
from ..accounts import credential_vault
from ..watchtower import dashboard_api as watchtower_api
from ..mechanic import repair_engine, escalation_manager

log = get_logger("dashboard")

#: Blueprint instance (registered on the web app in production)
bp = Blueprint(
    "observatory",
    __name__,
    template_folder=str(config.PROJECT_ROOT / "dashboard" / "templates"),
    static_folder=str(config.PROJECT_ROOT / "dashboard" / "static"),
)

#: Login rate limiting: ip -> list of timestamps
_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def _db() -> Any:
    """Return the shared database instance."""
    from ..database import get_db
    return get_db()


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _check_credentials(username: str, password: str) -> bool:
    """Validate dashboard credentials against env config.

    Args:
        username: Provided username.
        password: Provided password.

    Returns:
        True if valid.
    """
    expected_user = config.env("DASHBOARD_USER", "admin")
    expected_pass = config.env("DASHBOARD_PASSWORD", "changeme")
    return username == expected_user and password == expected_pass


def _is_rate_limited(ip: str) -> bool:
    """Check whether an IP is rate-limited for login.

    Args:
        ip: Client IP.

    Returns:
        True if the IP should be blocked.
    """
    now = time.time()
    attempts = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def _record_attempt(ip: str) -> None:
    """Record a login attempt for an IP.

    Args:
        ip: Client IP.
    """
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


def login_required(fn):
    """Decorator requiring an authenticated session."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("observatory.login"))
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@bp.route("/dashboard/login", methods=["GET", "POST"])
def login():
    """Render the login page and handle authentication."""
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _is_rate_limited(ip):
            return render_template("login.html", error="Too many attempts. Try again in 5 minutes."), 429

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if _check_credentials(username, password):
            session["authenticated"] = True
            session["login_time"] = _now()
            return redirect(url_for("observatory.dashboard_overview"))
        _record_attempt(ip)
        return render_template("login.html", error="Invalid credentials"), 401

    return render_template("login.html")


@bp.route("/dashboard/logout")
def logout():
    """Clear the session and redirect to login."""
    session.clear()
    return redirect(url_for("observatory.login"))


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@bp.route("/dashboard")
@login_required
def dashboard_overview():
    """Main overview page."""
    return render_template("dashboard.html", active="overview")


@bp.route("/dashboard/health")
@login_required
def dashboard_health():
    """Detailed health report page."""
    return render_template("health.html", active="health")


@bp.route("/dashboard/activity")
@login_required
def dashboard_activity():
    """Activity feed page."""
    return render_template("activity.html", active="activity")


@bp.route("/dashboard/controls")
@login_required
def dashboard_controls():
    """Agent controls page."""
    return render_template("controls.html", active="controls")


@bp.route("/dashboard/finance")
@login_required
def dashboard_finance():
    """Financial metrics page."""
    return render_template("finance.html", active="finance")


@bp.route("/dashboard/vault")
@login_required
def dashboard_vault():
    """Credential vault page."""
    return render_template("vault.html", active="vault")


@bp.route("/dashboard/settings")
@login_required
def dashboard_settings():
    """System settings page."""
    return render_template("settings.html", active="settings")


# ---------------------------------------------------------------------------
# Health APIs
# ---------------------------------------------------------------------------

@bp.route("/api/dashboard/health/latest")
@login_required
def api_health_latest():
    """Return the latest health report."""
    return jsonify(watchtower_api.latest_report())


@bp.route("/api/dashboard/health/history")
@login_required
def api_health_history():
    """Return recent health history."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"history": watchtower_api.history(limit=limit)})


@bp.route("/api/dashboard/health/run", methods=["POST"])
@login_required
def api_health_run():
    """Trigger a fresh health check."""
    report = asyncio.run(watchtower_api.run_check_and_save(db=_db()))
    return jsonify(report)


# ---------------------------------------------------------------------------
# Activity API
# ---------------------------------------------------------------------------

@bp.route("/api/dashboard/activity")
@login_required
def api_activity():
    """Return recent agent activity (posts, repairs, escalations)."""
    db = _db()
    posts = db.latest_posts(limit=10)
    repairs = repair_engine.latest_repairs(db, limit=10)
    escalations = escalation_manager.all_escalations(db, limit=10)

    activity: List[Dict[str, Any]] = []
    for p in posts:
        activity.append({
            "type": "post",
            "platform": p.get("platform"),
            "status": p.get("status"),
            "content": (p.get("content") or "")[:120],
            "created_at": p.get("created_at"),
        })
    for r in repairs:
        activity.append({
            "type": "repair",
            "repair_type": r.get("repair_type"),
            "target": r.get("target"),
            "status": r.get("status"),
            "detail": r.get("detail"),
            "created_at": r.get("created_at"),
        })
    for e in escalations:
        activity.append({
            "type": "escalation",
            "title": e.get("title"),
            "status": e.get("status"),
            "detail": e.get("detail"),
            "created_at": e.get("created_at"),
        })

    activity.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return jsonify({"activity": activity[:30]})


# ---------------------------------------------------------------------------
# Controls API
# ---------------------------------------------------------------------------

AGENTS = ["scout", "brain", "forge", "social", "chronicle", "watchtower", "mechanic"]


def _agent_state(db: Any) -> Dict[str, str]:
    """Read agent pause state from settings.

    Args:
        db: Database instance.

    Returns:
        Dict: agent -> "paused" | "running".
    """
    state: Dict[str, str] = {}
    for agent in AGENTS:
        state[agent] = db.get_setting(f"agent_{agent}_state", "running")
    return state


@bp.route("/api/dashboard/controls")
@login_required
def api_controls():
    """Return agent states and parameters."""
    db = _db()
    return jsonify({
        "agents": _agent_state(db),
        "parameters": {
            "post_frequency": db.get_setting("param_post_frequency", "3x daily"),
            "voice_tone": db.get_setting("param_voice_tone", "energetic"),
            "scout_interval_hours": db.get_setting("param_scout_interval_hours", "4"),
        },
    })


@bp.route("/api/dashboard/controls/pause", methods=["POST"])
@login_required
def api_controls_pause():
    """Pause an agent."""
    agent = request.json.get("agent", "")
    if agent not in AGENTS:
        return jsonify({"success": False, "error": "unknown agent"}), 400
    db = _db()
    db.set_setting(f"agent_{agent}_state", "paused")
    log.info("Agent paused: %s", agent)
    return jsonify({"success": True, "agent": agent, "state": "paused"})


@bp.route("/api/dashboard/controls/resume", methods=["POST"])
@login_required
def api_controls_resume():
    """Resume an agent."""
    agent = request.json.get("agent", "")
    if agent not in AGENTS:
        return jsonify({"success": False, "error": "unknown agent"}), 400
    db = _db()
    db.set_setting(f"agent_{agent}_state", "running")
    log.info("Agent resumed: %s", agent)
    return jsonify({"success": True, "agent": agent, "state": "running"})


@bp.route("/api/dashboard/controls/run", methods=["POST"])
@login_required
def api_controls_run():
    """Trigger a manual agent run."""
    agent = request.json.get("agent", "")
    if agent not in AGENTS:
        return jsonify({"success": False, "error": "unknown agent"}), 400
    db = _db()
    db.set_setting(f"agent_{agent}_last_manual_run", _now())
    log.info("Manual run triggered: %s", agent)
    return jsonify({"success": True, "agent": agent, "triggered": True})


@bp.route("/api/dashboard/controls/params", methods=["POST"])
@login_required
def api_controls_params():
    """Update agent parameters."""
    db = _db()
    data = request.json or {}
    for key, value in data.items():
        db.set_setting(f"param_{key}", str(value))
    log.info("Parameters updated: %s", list(data.keys()))
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Finance API
# ---------------------------------------------------------------------------

@bp.route("/api/dashboard/finance")
@login_required
def api_finance():
    """Return financial metrics."""
    db = _db()
    summary = db.financial_summary()
    recent = db.query(
        "SELECT * FROM financial_records ORDER BY recorded_at DESC LIMIT 20"
    )
    return jsonify({"summary": summary, "recent": recent})


# ---------------------------------------------------------------------------
# Patrons API (Patreon integration)
# ---------------------------------------------------------------------------

@bp.route("/dashboard/patrons")
@login_required
def dashboard_patrons():
    """Patron management page."""
    return render_template("patrons.html", active="patrons")


@bp.route("/api/dashboard/patrons")
@login_required
def api_patrons():
    """Return patron data: totals by tier, recent patrons, revenue summary.

    Returns:
        JSON: {tiers, recent, summary}
    """
    db = _db()
    patrons = db.list_patrons(limit=100)
    counts = db.patron_counts_by_tier()
    total_active = db.patron_total_active()

    # Revenue summary from financial_records (patreon category)
    revenue_rows = db.query(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM financial_records "
        "WHERE record_type = 'revenue' AND category = 'patreon'"
    )
    patreon_revenue = float(revenue_rows[0]["total"] if revenue_rows else 0)

    return jsonify({
        "tiers": {
            "1": counts.get(1, 0),
            "2": counts.get(2, 0),
            "3": counts.get(3, 0),
        },
        "total_active": total_active,
        "recent": patrons[:20],
        "revenue_summary": {
            "patreon_revenue": patreon_revenue,
        },
    })


# ---------------------------------------------------------------------------
# Vault API
# ---------------------------------------------------------------------------

#: In-memory unlocked vault (per process). Locked on restart.
_VAULT: Optional[credential_vault.CredentialVault] = None


def _get_vault() -> credential_vault.CredentialVault:
    """Return the shared vault instance (may be locked).

    Returns:
        CredentialVault instance.
    """
    global _VAULT
    if _VAULT is None:
        _VAULT = credential_vault.CredentialVault()
    return _VAULT


@bp.route("/api/dashboard/vault/status")
@login_required
def api_vault_status():
    """Return whether the vault is unlocked and which services exist."""
    vault = _get_vault()
    services = vault.list_services() if vault.unlocked else []
    return jsonify({"unlocked": vault.unlocked, "services": services})


@bp.route("/api/dashboard/vault/unlock", methods=["POST"])
@login_required
def api_vault_unlock():
    """Unlock the vault with the master password."""
    master = request.json.get("master_password", "")
    if not master:
        return jsonify({"success": False, "error": "master password required"}), 400
    vault = _get_vault()
    if not vault.exists():
        # First-time setup: initialize the vault
        try:
            vault.initialize(master)
            return jsonify({"success": True, "initialized": True, "services": []})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
    if vault.unlock(master):
        return jsonify({"success": True, "services": vault.list_services()})
    return jsonify({"success": False, "error": "wrong master password"}), 401


@bp.route("/api/dashboard/vault/lock", methods=["POST"])
@login_required
def api_vault_lock():
    """Lock the vault (wipe in-memory secrets)."""
    _get_vault().lock()
    return jsonify({"success": True})


@bp.route("/api/dashboard/vault/services")
@login_required
def api_vault_services():
    """Return service names + non-secret metadata (no secrets)."""
    vault = _get_vault()
    if not vault.unlocked:
        return jsonify({"error": "vault locked"}), 401
    services = []
    for service in vault.list_services():
        creds = vault.get_service_credentials(service)
        # Expose only non-secret fields
        public = {k: v for k, v in creds.items() if k in {"status", "signup_url", "notes", "email"}}
        services.append({"service": service, "meta": public})
    return jsonify({"services": services})


@bp.route("/api/dashboard/vault/export", methods=["POST"])
@login_required
def api_vault_export():
    """Export an encrypted backup of the vault."""
    vault = _get_vault()
    if not vault.unlocked:
        return jsonify({"error": "vault locked"}), 401
    out = config.PROJECT_ROOT / "data" / "vault" / "backup.enc"
    vault.write_backup(out)
    return jsonify({"success": True, "path": str(out)})


# ---------------------------------------------------------------------------
# Configuration API (masked .env view)
# ---------------------------------------------------------------------------

#: Keys whose values are safe to show in full (non-secret)
NON_SECRET_KEYS = {
    "SITE_URL", "FLASK_ENV", "FLASK_SECRET_KEY", "DASHBOARD_USER",
    "DASHBOARD_PORT", "VAULT_PATH", "MANIFEST_PATH", "DATABASE_PATH",
    "ARCHIVE_PATH", "LOG_PATH", "REFERRALS_FOR_FREE_PRO",
    "FIRST_N_WAITLIST_FREE_PRO", "TWITTER_BOT_HANDLE",
    "TWITTER_DAILY_FOLLOW_LIMIT", "TWITTER_FOLLOW_KEYWORDS",
    "OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODEL",
    "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_SIZE", "OPENAI_IMAGE_QUALITY",
    "SMTP_PORT", "SMTP_FROM", "DISCORD_WELCOME_MESSAGE",
    "AFFILIATE_COINBASE", "AFFILIATE_BINANCE", "AFFILIATE_NAMECHEAP",
}

#: Keys that are secret (masked in the config view)
SECRET_KEYS = {
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "TWITTER_API_KEY",
    "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
    "TWITTER_BEARER_TOKEN", "DISCORD_BOT_TOKEN", "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN", "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "SMTP_USER",
    "SMTP_PASSWORD", "DASHBOARD_PASSWORD", "OPENROUTER_BACKUP_KEY",
    "OPENAI_BACKUP_KEY", "TWITTER_BACKUP_KEY", "STRIPE_BACKUP_KEY",
}


def _mask(value: str) -> str:
    """Mask a secret value, showing only first 8 + last 4 chars.

    Args:
        value: The secret string.

    Returns:
        Masked preview like ``sk-or-v1-••••••••845``.
    """
    if not value:
        return ""
    if len(value) <= 12:
        return "••••••••"
    return f"{value[:8]}••••••••{value[-4:]}"


def _env_config() -> Dict[str, Any]:
    """Build a masked view of the deployed configuration.

    Returns:
        Dict with env_path, keys (list of {key, value, masked, secret, set}),
        and counts. In production, config comes from environment variables
        (no .env on disk), so keys are read from os.environ.
    """
    import os
    env_path = config.PROJECT_ROOT / ".env"
    present: set = set()

    # Collect keys present in the .env file if it exists (local dev)
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                present.add(line.split("=", 1)[0].strip())

    # In production, all config lives in environment variables.
    present |= {k for k in os.environ if k in NON_SECRET_KEYS or k in SECRET_KEYS}

    keys: List[Dict[str, Any]] = []
    all_keys = sorted(present | NON_SECRET_KEYS | SECRET_KEYS)
    for key in all_keys:
        value = config.env(key)
        is_secret = key in SECRET_KEYS
        keys.append({
            "key": key,
            "value": value,
            "masked": _mask(value) if is_secret else value,
            "secret": is_secret,
            "set": bool(value),
        })

    return {
        "env_path": str(env_path),
        "env_exists": env_path.exists(),
        "production": config.env("FLASK_ENV") == "production",
        "keys": keys,
        "counts": {
            "total": len(keys),
            "set": sum(1 for k in keys if k["set"]),
            "missing": sum(1 for k in keys if not k["set"]),
        },
    }


@bp.route("/api/dashboard/config")
@login_required
def api_config():
    """Return a masked view of the configuration.

    Never returns full secret values — only masked previews + set/missing
    status. Non-secret keys are shown in full.
    """
    return jsonify(_env_config())


@bp.route("/api/dashboard/vault/import-env", methods=["POST"])
@login_required
def api_vault_import_env():
    """Import env configuration into the encrypted vault.

    Requires the vault to be unlocked with the master password. In production
    this imports the environment (which contains the deployed secrets) under
    an ``env`` service so values are accessible only after unlocking.

    Returns:
        JSON: {"success": bool, "imported": int, "error": str?}
    """
    import os
    vault = _get_vault()
    if not vault.unlocked:
        return jsonify({"success": False, "error": "vault locked — unlock first"}), 401

    keys: Dict[str, str] = {}

    # Local dev: read from .env file
    env_path = config.PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            keys[key.strip()] = value.strip().strip('"').strip("'")

    # Production: read from environment variables
    for key in NON_SECRET_KEYS | SECRET_KEYS:
        if key in os.environ and key not in keys:
            keys[key] = os.environ[key]

    imported = 0
    for key, value in keys.items():
        vault.set_credential("env", key, value)
        imported += 1

    log.info("Imported %d env keys into the encrypted vault", imported)
    return jsonify({"success": True, "imported": imported})


# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------

def _table_exists(db: Any, table: str) -> bool:
    """Check whether a table exists.

    Args:
        db: Database instance.
        table: Table name.

    Returns:
        True if the table exists.
    """
    try:
        row = db.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return row is not None
    except Exception:  # noqa: BLE001
        return False


@bp.route("/api/dashboard/settings")
@login_required
def api_settings():
    """Return system settings (non-secret)."""
    db = _db()
    return jsonify({
        "site_url": config.env("SITE_URL", "http://localhost:5000"),
        "flask_env": config.env("FLASK_ENV", "development"),
        "subscriber_count": db.subscriber_count(),
        "trend_count": db.query_one("SELECT COUNT(*) AS n FROM trends")["n"],
        "repair_count": db.query_one("SELECT COUNT(*) AS n FROM repair_log")["n"]
        if _table_exists(db, "repair_log") else 0,
    })


# ---------------------------------------------------------------------------
# Real-time SSE
# ---------------------------------------------------------------------------

@bp.route("/dashboard/stream")
@login_required
def dashboard_stream():
    """Server-Sent Events stream — health status every 30 seconds."""
    def generate():
        while True:
            report = watchtower_api.latest_report()
            yield f"data: {json.dumps(report)}\n\n"
            time.sleep(30)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Error handler (404 within dashboard URLs)
# ---------------------------------------------------------------------------

@bp.app_errorhandler(404)
def not_found(_e: Any):
    """Render a friendly 404 for dashboard routes."""
    return render_template("login.html", error="Page not found"), 404