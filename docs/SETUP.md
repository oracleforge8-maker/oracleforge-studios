# OracleForge Studios — Setup Guide

Complete step-by-step installation, API credential setup, account creation flow,
dashboard access, credential retrieval, deployment, and the 72-hour roadmap.

---

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Tested on 3.14 |
| pip | latest | `python -m pip install --upgrade pip` |
| Node.js (optional) | 18+ | Only needed for n8n |
| Docker (optional) | latest | For containerized deployment |
| Chrome (optional) | latest | For browser-assisted account signups |

---

## 2. Install Python Dependencies

```bash
cd OracleForge
pip install -r requirements.txt
```

Installs: `python-dotenv`, `PyYAML`, `requests`, `aiohttp`, `Flask`,
`Flask-Cors`, `openai`, `tweepy`, `discord.py`, `stripe`, `matplotlib`,
`Pillow`, `cryptography`, `selenium`, `APScheduler`, `pytest`, `pytest-asyncio`.

---

## 3. Configure Environment

```bash
cp config/.env.template .env
```

Key settings:

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | The Brain (DeepSeek Flash) — required |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | Observatory login — **change these** |
| `VAULT_PATH` / `MANIFEST_PATH` | Encrypted vault + manifest locations |
| `OPENROUTER_BACKUP_KEY` etc. | Backup keys for The Mechanic rotation |
| `SMTP_HOST` / `ALERT_EMAIL` | Optional email alerts |

---

## 4. Initialize Database + Vault

```bash
python main.py --init-db
python main.py --vault-init        # prompts for a master password (store it safely!)
```

The vault encrypts all credentials at rest using Fernet + PBKDF2-HMAC-SHA256
(600k iterations). The master password is **never stored**.

---

## 5. Account Creation Flow (Registration Orchestrator)

> **Compliance note:** Google, X, OpenAI, and Stripe require human verification
> (CAPTCHA, SMS, payment method). The orchestrator generates strong unique
> credentials, opens each official signup URL, and pauses for the human to
> complete only the steps the platform requires. This is the ToS-compliant
> approach — fully automated signup would flag/ban the accounts.

```bash
# Generate candidate credentials + open signup pages in your browser
python main.py --register-accounts

# Or generate candidate credentials only (no browser)
python main.py --register-accounts --non-interactive
```

Services orchestrated:

| Service | Signup URL | Human step |
|---------|-----------|------------|
| Gmail (master identity) | accounts.google.com/signup | CAPTCHA + SMS |
| Twitter/X (@ChadSatoshi) | x.com/i/flow/signup | CAPTCHA + email |
| Discord (5 channels) | discord.com/register | CAPTCHA + email |
| LinkedIn (B2B profile) | linkedin.com/signup | CAPTCHA + email |
| OpenAI (DALL-E 3) | platform.openai.com/signup | Phone verification |
| Stripe (test mode) | dashboard.stripe.com/register | Business details |
| Namecheap (domain) | namecheap.com/myaccount/signup | Email verification |

After the human completes each signup, confirm it:

```bash
python main.py --vault-unlock       # unlock + list services
```

The orchestrator stores all confirmed credentials in the encrypted vault and
writes a status report to `data/registry_status.json`.

---

## 6. The Observatory Dashboard

```bash
python main.py --serve-dashboard --port 5001
# → http://localhost:5001/dashboard
```

Login with `DASHBOARD_USER` / `DASHBOARD_PASSWORD`.

| Page | Purpose |
|------|---------|
| `/dashboard` | Health overview + quick stats |
| `/dashboard/health` | Detailed color-coded checks (auto-refresh 30s) |
| `/dashboard/activity` | Posts, repairs, escalations feed |
| `/dashboard/controls` | Pause/resume agents, trigger runs, tune params |
| `/dashboard/finance` | API costs, revenue, net |
| `/dashboard/vault` | Encrypted credential management (master password) |
| `/dashboard/settings` | System info + security notes |

Real-time updates via Server-Sent Events (`/dashboard/stream`).

---

## 7. Credential Retrieval (The Archive)

### Via the dashboard
1. Log in → `/dashboard/vault`
2. Enter the master password → unlock
3. View service statuses, export an encrypted backup

### Via the manifest (offline)
```bash
python main.py --manifest
# → writes data/vault/manifest.enc (encrypted)
```

Decrypt the manifest:
```bash
python -c "from src.accounts.manifest import decrypt_manifest; from pathlib import Path; import json; print(json.dumps(decrypt_manifest(Path('data/vault/manifest.enc'), '<master>'), indent=2))"
```

The manifest contains all usernames, passwords, API keys, account URLs, and
admin access links — encrypted with the master password.

---

## 8. Self-Management (Watchtower + Mechanic)

```bash
# Health check (every 30 min via scheduler; becomes hourly after 24h stable)
python main.py --run-watchtower

# Repair latest health issues
python main.py --run-mechanic
```

The Mechanic automatically:
- Retries failed social posts (up to 3 times)
- Reconnects stuck database connections
- Rotates API keys when rate-limited (uses `*_BACKUP_KEY` env vars)
- Writes a restart flag for the web worker
- Clears stale lock files
- Escalates to a human (dashboard alert) when a repair fails

---

## 9. Verify Components

```bash
python main.py --status
python main.py --run-scout
python main.py --run-brain --mode analysis
python main.py --run-forge --type brand
python main.py --run-social --platform twitter --social-mode radar_posts
python main.py --run-chronicle --chronicle-mode archive
python main.py --run-watchtower
python main.py --serve-web --port 5000
python main.py --serve-dashboard --port 5001
```

---

## 10. Orchestration

### Built-in scheduler
```bash
python main.py --scheduler
```

### n8n (production)
1. `npm install -g n8n && n8n start` → http://localhost:5678
2. Import `n8n/workflows.json`
3. Workflows: Scout Cycle (4h), Radar Posts (3x daily), Mention Replies (2h),
   Newsletter (Fri 10:00), Weekly Report (Sun 18:00), On-Demand Image (webhook)

### Docker
```bash
docker compose up -d
# Web: http://localhost:5000
# Dashboard: http://localhost:5001
# n8n: http://localhost:5678
```

---

## 11. Testing

```bash
pytest tests/ -v    # 49 tests
```

Covers: Scout, Brain, Chronicler, web pages/APIs, credential vault (encryption,
manifest round-trip), Watchtower checks, Mechanic repairs + escalations, and all
dashboard pages/APIs.

---

## 12. Deployment

### Local
```bash
python main.py --serve-web --port 5000
python main.py --serve-dashboard --port 5001
```

### Cloud (VPS / Railway / Render)
1. Push to GitHub
2. Deploy with `Dockerfile` + `docker-compose.yml`
3. Set all `.env` values as environment variables
4. Mount persistent volumes for `data/` and `logs/`
5. Use HTTPS (reverse proxy) to protect dashboard sessions

---

## 13. 72-Hour Implementation Roadmap

| Hours | Milestone | Deliverables |
|-------|-----------|--------------|
| 0–8 | Environment & foundation | Python deps, `.env`, DB schema, logger, utils, CLI |
| 8–24 | The Scout | Twitter/Pump.fun/CMC/DEXScreener/Reddit scrapers |
| 24–40 | The Brain | OpenRouter client, prompt templates, ChadSatoshi voice |
| 40–48 | Forge + Social | DALL-E 3 + SVG fallback, Twitter/Discord/LinkedIn clients |
| 48–56 | Website | All 7 pages, responsive dark theme, live demo, forms |
| 56–64 | The Chronicler | JSON archival, financial tracking, weekly reports |
| 64–72 | Orchestration & polish | n8n, Docker, tests, docs, end-to-end verification |
| +8 | Identity & vault | Encrypted vault, registration orchestrator, manifest |
| +8 | Watchtower + Mechanic | Health checks, self-healing, escalations |
| +8 | Observatory | Secure dashboard (7 pages, SSE real-time) |

---

## 14. Troubleshooting

| Problem | Fix |
|---------|-----|
| `UnicodeEncodeError` on Windows | Handled — `main.py` reconfigures stdout to UTF-8 |
| Vault "already exists" | Use `--vault-unlock` instead of `--vault-init` |
| Wrong master password | The vault is unrecoverable without it — keep it safe |
| Dashboard login locked | Rate-limited (5 attempts/5 min) — wait and retry |
| Mechanic escalates API key | Set `*_BACKUP_KEY` env vars for automatic rotation |
| Website shows critical in Watchtower | Start the web server (`--serve-web`) |
| Port 5001 in use | `python main.py --serve-dashboard --port 5002` |

---

## 15. Security Notes

- **Never commit `.env`** — it contains real API keys
- The vault + manifest are encrypted at rest; only the master password decrypts them
- Dashboard sessions require login; login is rate-limited
- Use HTTPS in production
- Social bots run in **dry-run mode** until real credentials are added
- All API keys are read from environment variables — never hardcoded