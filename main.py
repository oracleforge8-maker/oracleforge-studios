#!/usr/bin/env python3
"""OracleForge Studios — main entry point and orchestrator.

Usage:
    python main.py --init-db
    python main.py --run-scout [--sources twitter,pumpfun,cmc,reddit,dexscreener]
    python main.py --run-brain [--mode analysis|social|newsletter|voice_refresh]
    python main.py --run-forge [--type brand|business|meme] [--coin COIN] [--quote QUOTE]
    python main.py --run-social [--platform twitter|discord|linkedin] [--dry-run] [--social-mode MODE]
    python main.py --run-chronicle [--chronicle-mode archive|report]
    python main.py --serve-web [--port 5000]
    python main.py --serve-dashboard [--port 5001]
    python main.py --run-watchtower          # health check + save report
    python main.py --run-mechanic            # process latest health report + repair
    python main.py --register-accounts [--non-interactive]
    python main.py --vault-init              # create encrypted vault (prompts for master password)
    python main.py --vault-unlock            # unlock vault + print service list
    python main.py --manifest                # write encrypted credential manifest
    python main.py --all                     # full pipeline: scout -> brain -> chronicle
    python main.py --status                  # print config + DB summary
    python main.py --scheduler               # long-running scheduler per config/schedule.yaml

Each subcommand is independent — a failure in one agent never blocks the
others (every agent catches its own exceptions and logs them).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

# Windows consoles default to cp1252 which cannot encode emoji used in
# log/status output. Reconfigure to UTF-8 (with lossy replacement) so the
# system never crashes on `print()` or logging of emoji-containing strings.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is importable when running from anywhere
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config            # noqa: E402
from src.logger import get_logger  # noqa: E402

log = get_logger("main")


# ---------------------------------------------------------------------------
# Core agent runners
# ---------------------------------------------------------------------------

def run_init_db() -> None:
    """Create/verify the SQLite schema and print a confirmation."""
    from src.database import Database
    db = Database()
    log.info("Database initialized at %s", db.path)
    print(f"✅ Database initialized at {db.path}")


def run_scout(sources: str = "") -> None:
    """Run The Scout scraper agents.

    Args:
        sources: Comma-separated source filter (empty = all configured).
    """
    from src.agents.scout import run_scout as scout_main
    asyncio.run(scout_main(sources=sources))


def run_brain(mode: str = "analysis", limit: int = 20) -> None:
    """Run The Brain AI processing.

    Args:
        mode: analysis | social | newsletter | voice_refresh.
        limit: Max trend rows to feed the model.
    """
    from src.agents.brain import run_brain as brain_main
    result = asyncio.run(brain_main(mode=mode, limit=limit))

    # Newsletter result: dict with "subject"/"body"
    if isinstance(result, dict) and "subject" in result and "body" in result:
        print(f"📧 SUBJECT: {result['subject']}\n")
        print(result["body"])
    # Analysis result: dict with narratives/summary
    elif isinstance(result, dict):
        print("Analysis result:")
        print(result.get("summary", "No summary"))
        for n in result.get("narratives", []):
            print(f"  - {n.get('name')}: {n.get('insight')}")
    # Social posts / voice refresh: lists or strings
    elif isinstance(result, list):
        print("Generated posts:")
        for p in result:
            print(f"  > {p}")
    elif result:
        print(result)


def run_forge(image_type: str = "brand", coin: str = "", quote: str = "") -> None:
    """Run The Forge image generation.

    Args:
        image_type: brand | business | meme.
        coin: Coin name for business images.
        quote: Fun quote for meme images.
    """
    from src.agents.forge import run_forge as forge_main
    asyncio.run(forge_main(image_type=image_type, coin=coin, quote=quote))


def run_social(platform: str = "twitter", dry_run: bool = True, mode: str = "") -> None:
    """Run social media agents.

    Args:
        platform: twitter | discord | linkedin.
        dry_run: If True, logs posts to DB but doesn't send them.
        mode: Optional twitter sub-mode (radar_posts, replies, follow,
              celebrity_engagement).
    """
    from src.agents.social_router import run_social as social_main
    count = asyncio.run(social_main(platform=platform, dry_run=dry_run, mode=mode))
    print(f"✅ {platform.upper()} agent: {count} action(s) taken")
    log.info("%s agent complete: %d actions", platform, count)


def run_chronicle(mode: str = "archive") -> None:
    """Run The Chronicler archival/reporting.

    Args:
        mode: archive | report | daily.
    """
    from src.agents.chronicler import run_chronicle as chronicle_main
    asyncio.run(chronicle_main(mode=mode))


def serve_web(port: int = 5000) -> None:
    """Start the Flask website.

    Args:
        port: Port to bind (default 5000).
    """
    from web.server import app
    log.info("Starting OracleForge web at http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=(config.env("FLASK_ENV") == "development"))


# ---------------------------------------------------------------------------
# Expansion runners (Watchtower, Mechanic, Dashboard, Accounts)
# ---------------------------------------------------------------------------

def serve_dashboard(port: int = 5001) -> None:
    """Start the Observatory dashboard.

    Args:
        port: Port to bind (default 5001).
    """
    from src.dashboard.server import app as dash_app
    log.info("Starting Observatory dashboard at http://localhost:%d", port)
    dash_app.run(host="0.0.0.0", port=port, debug=(config.env("FLASK_ENV") == "development"))


def run_watchtower() -> None:
    """Run a Watchtower health check and persist the report."""
    from src.watchtower import health_checker, reporter
    report = asyncio.run(health_checker.run_health_check())
    reporter.save_report(report)
    print(f"🩺 Watchtower: {report['overall']} "
          f"({report['summary']['ok']} ok, {report['summary']['warning']} warn, "
          f"{report['summary']['critical']} crit)")
    for check in report["checks"]:
        if check["level"] != "ok":
            print(f"  [{check['level']}] {check['name']}: {check['detail']}")


def run_mechanic() -> None:
    """Run The Mechanic on the latest health report."""
    from src.watchtower import dashboard_api
    from src.mechanic import repair_engine
    from src.database import get_db

    db = get_db()
    latest = dashboard_api.latest_report()
    if not latest.get("generated_at"):
        print("⚠️ No health report yet — run --run-watchtower first")
        return
    summary = repair_engine.run_mechanic(latest, db=db)
    print(f"🔧 Mechanic: {len(summary['repairs'])} repair(s), escalated={summary['escalated']}")
    for r in summary["repairs"]:
        print(f"  - {r['check']}: {r['repair']} ({r['detail']})")


def register_accounts(interactive: bool = True) -> None:
    """Run the registration orchestrator.

    Args:
        interactive: If True, opens browsers for human-verified signups.
    """
    from src.accounts.credential_vault import CredentialVault
    from src.accounts.registration_orchestrator import RegistrationOrchestrator

    vault = CredentialVault()
    if not vault.exists():
        print("🔐 Vault not initialized. Run: python main.py --vault-init")
        return
    master = getpass.getpass("Master password: ")
    if not vault.unlock(master):
        print("❌ Wrong master password")
        return

    orchestrator = RegistrationOrchestrator(vault)
    status = orchestrator.run(interactive=interactive)
    print("\n📋 Registration status:")
    for service, info in status.items():
        print(f"  {service}: {info.get('status')} — {info.get('url', '')}")


def vault_init() -> None:
    """Initialize the encrypted credential vault."""
    from src.accounts.credential_vault import CredentialVault

    vault = CredentialVault()
    if vault.exists():
        print("❌ Vault already exists")
        return
    master = getpass.getpass("Choose a master password (store it safely!): ")
    confirm = getpass.getpass("Confirm master password: ")
    if master != confirm:
        print("❌ Passwords do not match")
        return
    vault.initialize(master)
    print(f"✅ Vault initialized at {vault.path}")


def vault_unlock() -> None:
    """Unlock the vault and list services."""
    from src.accounts.credential_vault import CredentialVault

    vault = CredentialVault()
    if not vault.exists():
        print("❌ Vault not found. Run: python main.py --vault-init")
        return
    master = getpass.getpass("Master password: ")
    if not vault.unlock(master):
        print("❌ Wrong master password")
        return
    services = vault.list_services()
    print(f"✅ Vault unlocked. Services: {', '.join(services) if services else '(none)'}")


def write_manifest() -> None:
    """Write the encrypted credential manifest."""
    from src.accounts.credential_vault import CredentialVault
    from src.accounts import manifest

    vault = CredentialVault()
    if not vault.exists():
        print("❌ Vault not found. Run: python main.py --vault-init")
        return
    master = getpass.getpass("Master password: ")
    if not vault.unlock(master):
        print("❌ Wrong master password")
        return
    path = manifest.write_manifest(vault, master)
    print(f"✅ Encrypted manifest written: {path}")
    print("   Decrypt with: python -c \"from src.accounts.manifest import decrypt_manifest; "
          "from pathlib import Path; print(decrypt_manifest(Path(r'<path>'), '<master>'))\"")


# ---------------------------------------------------------------------------
# Pipeline / status / scheduler
# ---------------------------------------------------------------------------

def run_all() -> None:
    """Run the full autonomous cycle: scout -> brain -> chronicle.

    Each step is wrapped so one failure does not stop the rest.
    """
    log.info("🚀 OracleForge full pipeline starting")
    steps = [
        ("scout", lambda: run_scout()),
        ("brain", lambda: run_brain(mode="analysis")),
        ("chronicle-archive", lambda: run_chronicle(mode="archive")),
    ]
    results = []
    for name, fn in steps:
        try:
            fn()
            results.append((name, "OK"))
            log.info("✅ Step %s completed", name)
        except Exception as exc:  # noqa: BLE001 — keep pipeline alive
            results.append((name, f"FAILED: {exc}"))
            log.error("❌ Step %s failed: %s", name, exc)
    print("\nPipeline summary:")
    for name, status in results:
        print(f"  {name}: {status}")


def show_status() -> None:
    """Print configuration + DB summary for debugging."""
    print(config.summary())
    print()
    try:
        from src.database import get_db
        db = get_db()
        print(f"📊 Subscribers: {db.subscriber_count()}")
        print(f"📊 Trends stored: {db.query_one('SELECT COUNT(*) AS n FROM trends')['n']}")
        print(f"💰 Financials: {db.financial_summary()}")
        posts = db.latest_posts(limit=3)
        print(f"📝 Recent posts: {len(posts)}")
        for p in posts:
            print(f"   [{p['platform']}/{p['status']}] {p['content'][:60]}...")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load DB summary: %s", exc)


def run_scheduler() -> None:
    """Long-running scheduler based on config/schedule.yaml.

    Minimal cron implementation — checks due jobs each minute. Suitable
    for local dev; for production prefer n8n workflows (n8n/workflows.json).
    """
    from src.scheduler import Scheduler
    sched = Scheduler()
    log.info("Scheduler starting (Ctrl+C to stop)...")
    try:
        sched.run_forever()
    except KeyboardInterrupt:
        log.info("Scheduler stopped by user")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        Configured argparse parser.
    """
    parser = argparse.ArgumentParser(
        prog="OracleForge",
        description="AI-powered meme coin intelligence studio",
    )
    parser.add_argument("--init-db", action="store_true", help="Initialize the SQLite database")
    parser.add_argument("--run-scout", action="store_true", help="Run The Scout scrapers")
    parser.add_argument("--sources", type=str, default="",
                        help="Comma-separated scout sources (twitter,pumpfun,cmc,reddit,dexscreener)")
    parser.add_argument("--run-brain", action="store_true", help="Run The Brain AI processing")
    parser.add_argument("--mode", type=str, default="analysis",
                        choices=["analysis", "social", "newsletter", "voice_refresh"],
                        help="Brain mode")
    parser.add_argument("--limit", type=int, default=20, help="Max data rows for Brain")
    parser.add_argument("--run-forge", action="store_true", help="Run The Forge image generation")
    parser.add_argument("--type", type=str, default="brand",
                        choices=["brand", "business", "meme"], help="Forge image type")
    parser.add_argument("--coin", type=str, default="", help="Coin name (business images)")
    parser.add_argument("--quote", type=str, default="", help="Fun quote (meme images)")
    parser.add_argument("--run-social", action="store_true", help="Run social agents")
    parser.add_argument("--platform", type=str, default="twitter",
                        choices=["twitter", "discord", "linkedin"], help="Social platform")
    parser.add_argument("--social-mode", type=str, default="",
                        choices=["radar_posts", "replies", "follow", "celebrity_engagement"],
                        help="Twitter sub-mode (default: radar_posts)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry-run mode (default; logs without sending)")
    parser.add_argument("--run-chronicle", action="store_true", help="Run The Chronicler")
    parser.add_argument("--chronicle-mode", type=str, default="archive",
                        choices=["archive", "report"], help="Chronicler mode (default: archive)")
    parser.add_argument("--serve-web", action="store_true", help="Start the website")
    parser.add_argument("--serve-dashboard", action="store_true", help="Start the Observatory dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Web/dashboard port")
    parser.add_argument("--run-watchtower", action="store_true", help="Run a Watchtower health check")
    parser.add_argument("--run-mechanic", action="store_true", help="Run The Mechanic on latest health report")
    parser.add_argument("--register-accounts", action="store_true", help="Run the registration orchestrator")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Registration without opening browsers (candidate creds only)")
    parser.add_argument("--vault-init", action="store_true", help="Initialize the encrypted credential vault")
    parser.add_argument("--vault-unlock", action="store_true", help="Unlock the vault and list services")
    parser.add_argument("--manifest", action="store_true", help="Write the encrypted credential manifest")
    parser.add_argument("--all", action="store_true", help="Run full pipeline (scout->brain->archive)")
    parser.add_argument("--status", action="store_true", help="Show config/DB status")
    parser.add_argument("--scheduler", action="store_true", help="Run the built-in scheduler")
    return parser


def main(argv: Optional[list] = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argv list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    log.debug("CLI args: %s", vars(args))

    try:
        if args.init_db:
            run_init_db()
        elif args.run_scout:
            run_scout(args.sources)
        elif args.run_brain:
            run_brain(args.mode, args.limit)
        elif args.run_forge:
            run_forge(args.type, args.coin, args.quote)
        elif args.run_social:
            run_social(args.platform, args.dry_run, args.social_mode)
        elif args.run_chronicle:
            run_chronicle(args.chronicle_mode)
        elif args.serve_web:
            serve_web(args.port)
        elif args.serve_dashboard:
            serve_dashboard(args.port)
        elif args.run_watchtower:
            run_watchtower()
        elif args.run_mechanic:
            run_mechanic()
        elif args.register_accounts:
            register_accounts(interactive=not args.non_interactive)
        elif args.vault_init:
            vault_init()
        elif args.vault_unlock:
            vault_unlock()
        elif args.manifest:
            write_manifest()
        elif args.all:
            run_all()
        elif args.status:
            show_status()
        elif args.scheduler:
            run_scheduler()
        else:
            parser.print_help()
        return 0
    except KeyboardInterrupt:
        log.info("Interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 — top-level safety net
        log.exception("Fatal error: %s", exc)
        print(f"\n❌ Fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())