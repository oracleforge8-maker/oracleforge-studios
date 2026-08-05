"""Gunicorn configuration for OracleForge Studios (production).

Used by the Procfile: ``gunicorn wsgi:app --config gunicorn.conf.py``

Bind port comes from the ``PORT`` env var (set by Render/Railway/Heroku).
"""

from __future__ import annotations

import os

#: Bind to the platform-provided port (default 5000 locally)
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

#: Number of worker processes (scale on Render via instance type)
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))

#: Worker class — threaded so Flask's small sync endpoints + SSE work
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

#: Timeout for slow requests (SSE keeps connections open; webhooks ok)
timeout = 120

#: Preload app for faster worker spawns
preload_app = True

#: Access + error logs to stdout (Render captures these)
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")