"""OracleForge Studios — production WSGI entry point.

Combines the marketing website and the Observatory dashboard into a single
Flask app served by Gunicorn (see Procfile / render.yaml).

Run locally:
    gunicorn wsgi:app --bind 0.0.0.0:5000
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config
from src.logger import get_logger
from web.server import app
from src.dashboard.blueprint import bp

log = get_logger("wsgi")

#: Mount the Observatory dashboard blueprint onto the marketing app
app.register_blueprint(bp)

#: Production secret key from environment (never hardcoded)
app.secret_key = config.env("FLASK_SECRET_KEY", "dev-secret")

log.info("OracleForge Studios WSGI app ready (env=%s)", config.env("FLASK_ENV", "development"))

#: Gunicorn expects a module-level ``app`` object
application = app