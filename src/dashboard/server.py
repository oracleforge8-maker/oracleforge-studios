"""The Observatory — dashboard server (local standalone mode).

In production, the dashboard runs as a Flask Blueprint mounted on the main
web app (see ``wsgi.py``). For local development, this module builds a
minimal Flask app and registers the same blueprint so you can run:

    python main.py --serve-dashboard --port 5001

All routes live in :mod:`src.dashboard.blueprint`.
"""

from __future__ import annotations

from flask import Flask

from .. import config
from .blueprint import bp

#: Flask app instance (local standalone dashboard)
app = Flask(__name__)
app.secret_key = config.env("FLASK_SECRET_KEY", "dev-secret")
app.register_blueprint(bp)