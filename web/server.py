"""OracleForge Flask web server.

Serves the multi-page marketing site and JSON APIs:

Pages:
    /            Home (hero + live trend widget + waitlist CTA)
    /tools       Product cards (Radar / Radar Pro / Forge)
    /live-demo   Live Scout feed
    /pricing     Tier comparison + referral + free trial
    /blog        The Degen Dispatch (latest 5 posts)
    /about       Cult of the Machine narrative
    /waitlist    Email capture + referral program

APIs:
    GET  /api/trends?limit=N     Latest trends (for live widgets)
    POST /api/waitlist           Add subscriber (email, name, referred_by)
    POST /api/newsletter         Subscribe to newsletter (email)

Run:
    python main.py --serve-web [--port 5000]
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from src import config
from src.logger import get_logger

log = get_logger("web")

#: Flask app instance (imported by main.py)
app = Flask(__name__)
app.secret_key = config.env("FLASK_SECRET_KEY", "dev-secret")
CORS(app)

#: Simple email validation regex
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db() -> Any:
    """Return the shared database instance.

    Returns:
        Database instance.
    """
    from src.database import get_db
    return get_db()


def _affiliate_links() -> Dict[str, str]:
    """Return affiliate link config for templates.

    Returns:
        Dict of affiliate URLs.
    """
    return {
        "affiliate_coinbase": config.env("AFFILIATE_COINBASE", "#"),
        "affiliate_binance": config.env("AFFILIATE_BINANCE", "#"),
        "affiliate_namecheap": config.env("AFFILIATE_NAMECHEAP", "#"),
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Render the home page."""
    return render_template("home.html", **_affiliate_links())


@app.route("/tools")
def tools():
    """Render the tools page."""
    return render_template("tools.html")


@app.route("/live-demo")
def live_demo():
    """Render the live demo page."""
    return render_template("live_demo.html")


@app.route("/pricing")
def pricing():
    """Render the pricing page."""
    return render_template("pricing.html")


@app.route("/blog")
def blog():
    """Render the blog page with the latest 5 posts."""
    db = _db()
    posts = db.latest_posts(limit=5)
    # Add a derived title for display
    for p in posts:
        p["title"] = _post_title(p)
    return render_template("blog.html", posts=posts)


@app.route("/about")
def about():
    """Render the about page."""
    return render_template("about.html")


@app.route("/waitlist")
def waitlist():
    """Render the waitlist page."""
    return render_template("waitlist.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/trends")
def api_trends():
    """Return the latest trends as JSON.

    Query params:
        limit: Max rows (default 20).

    Returns:
        JSON: {"trends": [...]}
    """
    try:
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 20

    db = _db()
    trends = db.latest_trends(limit=limit)
    return jsonify({"trends": trends})


@app.route("/api/waitlist", methods=["POST"])
def api_waitlist():
    """Add a subscriber to the waitlist.

    Form fields:
        email (required), name (optional), referred_by (optional).

    Returns:
        JSON: {"success": bool, "referral_code": str, "error": str?}
    """
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    referred_by = (request.form.get("referred_by") or "").strip()

    if not email or not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Please enter a valid email."}), 400

    db = _db()
    try:
        subscriber = db.add_subscriber(email, name=name, referred_by=referred_by)
        log.info("New waitlist subscriber: %s", email)
        return jsonify({
            "success": True,
            "referral_code": subscriber.get("referral_code", ""),
        })
    except Exception as exc:  # noqa: BLE001
        log.error("Waitlist signup failed: %s", exc)
        return jsonify({"success": False, "error": "Could not add you to the list."}), 500


@app.route("/api/newsletter", methods=["POST"])
def api_newsletter():
    """Subscribe an email to the newsletter (reuses waitlist table).

    Form fields:
        email (required).

    Returns:
        JSON: {"success": bool, "error": str?}
    """
    email = (request.form.get("email") or "").strip().lower()
    if not email or not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Please enter a valid email."}), 400

    db = _db()
    try:
        db.add_subscriber(email)
        log.info("Newsletter subscription: %s", email)
        return jsonify({"success": True})
    except Exception as exc:  # noqa: BLE001
        log.error("Newsletter subscribe failed: %s", exc)
        return jsonify({"success": False, "error": "Could not subscribe."}), 500


# ---------------------------------------------------------------------------
# Stripe webhook (production payments)
# ---------------------------------------------------------------------------

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events (subscriptions, payments).

    Verifies the signature using STRIPE_WEBHOOK_SECRET, then records the
    event in financial_records. Returns 200 to acknowledge receipt.

    Returns:
        JSON: {"received": True} on success, 400 on verification failure.
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        from config.stripe_config import verify_webhook
        event = verify_webhook(payload, sig_header)
    except Exception as exc:  # noqa: BLE001
        log.error("Stripe webhook verification failed: %s", exc)
        return jsonify({"error": "invalid signature"}), 400

    event_type = event.get("type", "unknown")
    log.info("Stripe webhook received: %s", event_type)

    db = _db()
    # Record revenue for relevant events
    if event_type in {"checkout.session.completed", "invoice.paid"}:
        data = event.get("data", {}).get("object", {})
        amount = data.get("amount_total") or data.get("amount_paid") or 0
        db.add_financial(
            "revenue", "stripe",
            float(amount) / 100.0,  # Stripe amounts are in cents
            f"stripe:{event_type}",
        )
        log.info("Stripe revenue recorded: $%.2f", float(amount) / 100.0)

    return jsonify({"received": True})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_title(post: Dict[str, Any]) -> str:
    """Derive a display title from a post.

    Args:
        post: Post row dict.

    Returns:
        A short title string.
    """
    content = post.get("content", "")
    # First line, truncated
    first_line = content.splitlines()[0] if content else "Untitled"
    return first_line[:60] + ("..." if len(first_line) > 60 else "")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_e: Any):
    """Render a friendly 404 page."""
    return render_template("base.html"), 404


@app.errorhandler(500)
def server_error(_e: Any):
    """Render a friendly 500 page."""
    return render_template("base.html"), 500