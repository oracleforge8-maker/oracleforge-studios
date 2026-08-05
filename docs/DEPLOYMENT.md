# OracleForge Studios — Production Deployment Guide (Render.com)

Deploy the complete OracleForge Studios system (public website + Observatory
dashboard + Stripe webhooks) to a live, HTTPS, publicly-accessible URL.

**Platform:** Render.com (free tier, auto-HTTPS, webhook support, auto-deploy
from GitHub).

---

## 1. What You'll Get

| Item | URL |
|------|-----|
| Public website | `https://oracleforge-studios.onrender.com` |
| Observatory dashboard | `https://oracleforge-studios.onrender.com/dashboard` |
| Stripe webhook endpoint | `https://oracleforge-studios.onrender.com/stripe/webhook` |

Both the website and dashboard run from **one app on one port** (required by
Render free tier). This was achieved by converting the dashboard into a Flask
Blueprint mounted on the marketing app (`wsgi.py`).

---

## 2. Files Already Created

| File | Purpose |
|------|---------|
| `wsgi.py` | Production entry — combines website + dashboard Blueprint |
| `Procfile` | Tells Render how to run: `gunicorn wsgi:app` |
| `runtime.txt` | Python 3.11.9 |
| `gunicorn.conf.py` | Binds `$PORT`, 1 worker, 4 threads, 120s timeout |
| `render.yaml` | Render Blueprint config (env vars + persistent disk) |
| `requirements.txt` | Includes `gunicorn` |
| `/stripe/webhook` route | Handles `checkout.session.completed` + `invoice.paid` → records revenue |

---

## 3. Step-by-Step Deployment

### Step 1 — Push to GitHub

```bash
cd C:\Users\misfi\Desktop\OracleForge

# NEVER commit the .env — .gitignore already protects it
git init
git add -A
git commit -m "OracleForge Studios - production ready"
git branch -M main

# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/oracleforge-studios.git
git push -u origin main
```

### Step 2 — Create the Render app

1. Go to https://dashboard.render.com and sign up (GitHub login is easiest)
2. Click **New → Blueprint**
3. Select your `oracleforge-studios` repo
4. Render reads `render.yaml` and provisions the service automatically
5. Click **Apply** → Render builds and deploys

### Step 3 — Set environment variables

In the Render dashboard, go to your **oracleforge-studios** service →
**Environment** and add every secret (these are marked `sync: false` in
`render.yaml`, so Render asks you to set them manually):

| Key | Value |
|-----|-------|
| `FLASK_ENV` | `production` (set by render.yaml) |
| `SITE_URL` | `https://oracleforge-studios.onrender.com` (set by render.yaml) |
| `FLASK_SECRET_KEY` | A long random string (e.g. from `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DASHBOARD_USER` | Your dashboard admin username |
| `DASHBOARD_PASSWORD` | A strong dashboard password |
| `OPENROUTER_API_KEY` | Your existing key |
| `OPENAI_API_KEY` | Optional (DALL-E) |
| `TWITTER_API_KEY` / `TWITTER_API_SECRET` / `TWITTER_ACCESS_TOKEN` / `TWITTER_ACCESS_SECRET` / `TWITTER_BEARER_TOKEN` | Optional (social) |
| `DISCORD_BOT_TOKEN` | Optional |
| `LINKEDIN_ACCESS_TOKEN` | Optional |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | Test keys |
| `STRIPE_PRICE_RADAR_PRO` / `STRIPE_PRICE_FORGE` | Price IDs (from `python -m config.stripe_config --setup`) |

Render also sets `DATABASE_PATH`, `ARCHIVE_PATH`, `LOG_PATH`, `VAULT_PATH`,
`MANIFEST_PATH` to the **persistent disk** (1 GB) so SQLite data survives
restarts.

### Step 4 — Configure Stripe webhook

1. Go to https://dashboard.stripe.com/test/webhooks
2. Click **Add endpoint**
3. URL: `https://oracleforge-studios.onrender.com/stripe/webhook`
4. Events to listen for:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
5. Click **Add endpoint**, then **Reveal signing secret** (`whsec_...`)
6. Set that as `STRIPE_WEBHOOK_SECRET` in Render → Environment
7. **Deploy** the service again (Render auto-deploys on env change)

### Step 5 — Custom domain (optional)

1. In Render → Settings → Custom Domain, add `oracleforge.ai`
2. At your DNS provider (Namecheap), add:
   - CNAME: `oracleforge.ai` → `oracleforge-studios.onrender.com`
   - CNAME: `www.oracleforge.ai` → `oracleforge-studios.onrender.com`
3. Render issues a free auto-renewing HTTPS certificate

---

## 4. Continuous Deployment

`render.yaml` has `autoDeploy: true`, so **every `git push` to `main`
automatically rebuilds and deploys the live site**. No manual steps.

```bash
git add -A && git commit -m "update" && git push
```

---

## 5. Verification Commands

```bash
# Website reachable (should return 200)
curl -s -o /dev/null -w "%{http_code}" https://oracleforge-studios.onrender.com/

# Dashboard login page reachable
curl -s -o /dev/null -w "%{http_code}" https://oracleforge-studios.onrender.com/dashboard/login

# Blog / pages
curl -s -o /dev/null -w "%{http_code}" https://oracleforge-studios.onrender.com/pricing
curl -s -o /dev/null -w "%{http_code}" https://oracleforge-studios.onrender.com/live-demo

# Stripe webhook endpoint responds (400 without valid signature = correct)
curl -s -X POST -o /dev/null -w "%{http_code}" https://oracleforge-studios.onrender.com/stripe/webhook

# Waitlist API works
curl -s -X POST https://oracleforge-studios.onrender.com/api/waitlist \
  -d "email=test@example.com"
```

Expected: `200 200 200 200 400` (webhook 400 is correct — it rejects unsigned
events, which is the secure behavior).

---

## 6. Running Agents in Production

The web service runs the site + dashboard 24/7. The agents (Scout, Brain, etc.)
are CLI tools — run them on-demand from Render's **Shell** tab:

```bash
# In Render → your service → Shell
python main.py --run-scout
python main.py --run-brain --mode analysis
python main.py --run-chronicle --chronicle-mode archive
python main.py --run-watchtower
```

For scheduled agents, either:
1. Use the **built-in scheduler** (`python main.py --scheduler`) — but this
   blocks the shell; better to use option 2:
2. Import `n8n/workflows.json` into an external n8n (or a Render Cron Job) that
   calls the CLI commands weekly/daily.

> **Free-tier note:** Render free web services sleep after 15 min of no traffic
> and wake on request. For truly 24/7 agents, upgrade to a paid instance or run
> the agent jobs on a separate always-on server.

---

## 7. Persistent Data

| Data | Path (persistent disk) |
|------|------------------------|
| SQLite database | `/opt/render/project/src/data/chronicler.db` |
| JSON archives | `/opt/render/project/src/data/archive` |
| Logs | `/opt/render/project/src/data/logs` |
| Encrypted vault | `/opt/render/project/src/data/vault/` |
| Weekly reports | `/opt/render/project/src/data/reports` |

The 1 GB disk survives restarts and redeploys.

---

## 8. Troubleshooting

| Problem | Fix |
|---------|-----|
| App crashes on boot | Check **Logs** tab — usually a missing env var. Add it in Environment. |
| 400 on Stripe webhook | `STRIPE_WEBHOOK_SECRET` wrong/missing — set it and redeploy |
| `no module named stripe` | `requirements.txt` has `stripe>=10.0.0` — check build logs |
| Website returns 500 on `/dashboard/*` | Wrong `DASHBOARD_USER`/`PASSWORD` — set them |
| Static CSS missing on dashboard | Should be fixed — templates use `url_for('observatory.static', ...)` |
| SQLite "database is locked" | Low traffic — check persistent disk is mounted at `data/` |
| App sleeps on free tier | Expected — first request wakes it (slow ~30s) |
| Secrets visible in logs | Never `print()` env values; the dashboard only shows masked values |

---

## 9. Going Live Checklist

- [ ] GitHub repo pushed (`.env` NOT in it)
- [ ] Render service deployed (green)
- [ ] All env vars set including `FLASK_SECRET_KEY` + `DASHBOARD_USER/PASSWORD`
- [ ] Stripe webhook endpoint added + `STRIPE_WEBHOOK_SECRET` set
- [ ] Website returns 200 at `/`
- [ ] Dashboard login works at `/dashboard`
- [ ] Waitlist signup saves to persistent DB
- [ ] (Optional) Custom domain `oracleforge.ai` configured
- [ ] (Optional) Paid instance for 24/7 agents