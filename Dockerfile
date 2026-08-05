# ============================================================
# OracleForge — Dockerfile
# Multi-stage: Python 3.11 slim + n8n for orchestration
# ============================================================

FROM python:3.11-slim AS base

# --- System deps ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps (cached layer) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- App code ---
COPY . .

# --- Non-root user for safety ---
RUN useradd -m oracleforge
USER oracleforge

# --- Volumes for persistent data ---
VOLUME ["/app/data", "/app/logs"]

# --- Default: run the web server ---
EXPOSE 5000
CMD ["python", "main.py", "--serve-web", "--port", "5000"]