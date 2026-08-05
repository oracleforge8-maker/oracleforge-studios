# OracleForge Studios 🔮⚒️

**We forge the memes. You ride the waves. 🌊**

OracleForge Studios is a **fully autonomous AI-powered production agency**. It
scrapes crypto trends, analyzes them with DeepSeek Flash, generates content in
the voice of **ChadSatoshi**, creates images, runs autonomous social accounts,
archives everything — and now **manages its own identity, monitors its own
health, repairs itself, and reports to a human via a secure dashboard**.

## The Agents

| Agent | Role |
|-------|------|
| 🕵️ **The Scout** | Async scrapers for Twitter/X, Pump.fun, CMC, DEXScreener, Reddit (every 4h) |
| 🧠 **The Brain** | DeepSeek Flash via OpenRouter — analysis, content, replies, newsletters |
| 🎨 **The Forge** | DALL-E 3 image generation with branded SVG/PNG fallback |
| 📣 **The Voice** | ChadSatoshi — autonomous Twitter/X, Discord, LinkedIn posting |
| 📚 **The Chronicler** | SQLite + daily JSON archive, financial tracking, weekly reports |
| 🔍 **The Watchtower** | Health monitoring every 30min (API, DB, social, website, logs) |
| 🔧 **The Mechanic** | Self-healing — retries posts, reconnects DB, rotates keys, restarts web |
| 🪟 **The Observatory** | Secure human dashboard (7 pages, real-time via SSE) |
| 🔐 **The Archive** | Encrypted credential vault (Fernet + PBKDF2, master password) |
| 📋 **Registration** | Secure account generation + orchestrator for Gmail/Twitter/Discord/LinkedIn/OpenAI/Stripe/Namecheap |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp config/.env.template .env
#   → add OPENROUTER_API_KEY (required for The Brain)
#   → set DASHBOARD_USER / DASHBOARD_PASSWORD (the Observatory login)

# 3. Initialize database + vault
python main.py --init-db
python main.py --vault-init            # prompts for master password

# 4. Run the full content pipeline
python main.py --all

# 5. Start the website + dashboard
python main.py --serve-web --port 5000
python main.py --serve-dashboard --port 5001
# → site: http://localhost:5000   |   dashboard: http://localhost:5001/dashboard
```

## Self-Management Commands

```bash
python main.py --run-watchtower        # health check (30-min cadence via scheduler)
python main.py --run-mechanic          # repair latest health issues
python main.py --register-accounts     # generate + orchestrate account signups
python main.py --register-accounts --non-interactive   # candidate creds only
python main.py --vault-unlock          # unlock vault + list services
python main.py --manifest              # write encrypted credential manifest
```

## The Observatory Dashboard

Secure access at `http://localhost:5001/dashboard` (login required):

- `/dashboard` — health overview + quick stats
- `/dashboard/health` — detailed checks with color-coded status
- `/dashboard/activity` — posts, repairs, and escalations feed
- `/dashboard/controls` — pause/resume agents, trigger runs, tune params
- `/dashboard/finance` — API costs, revenue, net
- `/dashboard/vault` — encrypted credential management (master password)
- `/dashboard/settings` — system info + security notes

Real-time updates via Server-Sent Events (`/dashboard/stream`, 30s).

## Testing

```bash
pytest tests/ -v    # 49 tests: core agents, vault, watchtower, mechanic, dashboard
```

## Documentation

- [SETUP.md](SETUP.md) — full installation, account creation flow, dashboard access, deployment
- [config/prompts.yaml](../config/prompts.yaml) — all ChadSatoshi prompt templates
- [config/schedule.yaml](../config/schedule.yaml) — orchestration schedule
- [config/health_config.yaml](../config/health_config.yaml) — Watchtower checks

## Disclaimer

OracleForge Studios is an intelligence and content tool. **Not financial
advice.** Always DYOR. Meme coins are extremely volatile — never invest more
than you can afford to lose. 🫡