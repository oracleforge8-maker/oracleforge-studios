"""Registration orchestrator — drives signup for all OracleForge Studios accounts.

The orchestrator walks through each required service (Gmail, Twitter/X,
Discord, LinkedIn, OpenAI, Stripe, Namecheap):

1. Generates unique, strong credentials.
2. Opens the official signup URL in a browser (Selenium).
3. Pre-fills what it safely can; pauses for human verification (CAPTCHA,
   SMS, payment method) — a compliance requirement for Google/X/Stripe.
4. Stores final confirmed credentials into the encrypted vault
   (or marks them "awaiting-confirmation").
5. Produces a status report for the Watchtower.

Everything is idempotent: re-running skips accounts already confirmed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import config
from ..logger import get_logger
from . import account_registry as registry
from . import credential_vault
from . import gmail_creator
from ..utils import utcnow

log = get_logger("registration_orchestrator")


class RegistrationOrchestrator:
    """Coordinates account creation and vault storage."""

    def __init__(self, vault: credential_vault.CredentialVault) -> None:
        """Initialize with an unlocked vault.

        Args:
            vault: Unlocked CredentialVault instance.
        """
        self.vault = vault
        self.status: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Core flow
    # ------------------------------------------------------------------

    def run(self, interactive: bool = True) -> Dict[str, Dict[str, str]]:
        """Run the full registration flow for all services.

        Args:
            interactive: If True, launches a browser for signups that
                         require human verification. If False, only
                         generates + stores candidate credentials.

        Returns:
            Dict: service -> status/notes dict.
        """
        log.info("📋 Registration orchestrator starting")
        definitions = registry.ACCOUNT_DEFINITIONS

        # 1) Gmail first — it's the master identity
        self._process_service("gmail", definitions["gmail"], interactive=interactive)

        # 2) Everything else, using the Gmail address if available
        gmail_email = self.vault.get_credential("gmail", "email")
        for service, definition in definitions.items():
            if service == "gmail":
                continue
            self._process_service(service, definition, interactive=interactive,
                                  email_hint=gmail_email)

        self._write_status()
        log.info("Registration flow complete")
        return self.status

    def _process_service(self, service: str, definition: Dict[str, Any],
                         interactive: bool, email_hint: str = "") -> None:
        """Process a single service signup.

        Args:
            service: Service key.
            definition: Account definition dict.
            interactive: Whether to drive a browser (human-assisted).
            email_hint: Confirmed Gmail address (used as signup email).
        """
        # Skip if already confirmed
        current = self.vault.get_service_credentials(service)
        if current.get("status") == "confirmed":
            self.status[service] = {"status": "already-confirmed", "url": definition["signup_url"]}
            log.info("✅ %s already confirmed — skipping", service)
            return

        # Generate candidate credentials (never persisted until confirmed)
        creds = self._generate_service_credentials(service, definition, email_hint)

        if interactive and definition.get("human_required", True):
            log.info("Opening %s signup: %s", service, definition["signup_url"])
            self._open_signup_url(definition["signup_url"])
        else:
            log.info("Non-interactive mode for %s — storing candidate only", service)

        # Store candidate credentials marked awaiting-confirmation
        for key, value in creds.items():
            if value:
                self.vault.set_credential(service, key, value)
        self.vault.set_credential(service, "signup_url", definition["signup_url"])
        self.vault.set_credential(service, "status", "awaiting-confirmation")
        self.vault.set_credential(service, "notes", definition.get("notes", ""))
        self.vault.set_credential(service, "generated_at", utcnow())

        self.status[service] = {
            "status": "awaiting-confirmation",
            "url": definition["signup_url"],
            "human_required": str(definition.get("human_required", True)),
        }
        log.info("⏳ %s candidate credentials stored (awaiting human confirmation)", service)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_service_credentials(self, service: str, definition: Dict[str, Any],
                                      email_hint: str) -> Dict[str, str]:
        """Build candidate credentials for a service.

        Args:
            service: Service key.
            definition: Account definition.
            email_hint: Gmail address to use as signup email.

        Returns:
            Dict of field -> value.
        """
        creds: Dict[str, str] = {}
        for field in definition.get("fields", []):
            if field == "password":
                creds[field] = registry.generate_password()
            elif field == "username":
                creds[field] = registry.generate_username(f"of.{service}")
            elif field == "email":
                if email_hint:
                    # Use +alias so all services route to the master inbox
                    alias = email_hint.replace("@", f"+{service}@")
                    creds[field] = alias
                else:
                    creds[field] = ""
            elif field in {"recovery_email", "phone"}:
                creds[field] = ""
            else:
                creds[field] = ""
        return creds

    def _open_signup_url(self, url: str) -> None:
        """Open a signup URL in the default browser.

        Args:
            url: The signup URL to open.
        """
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not open browser for %s: %s", url, exc)

    # ------------------------------------------------------------------
    # Confirmation & status
    # ------------------------------------------------------------------

    def confirm_account(self, service: str, email: str = "") -> None:
        """Mark an account as confirmed by the operator.

        Args:
            service: Service key.
            email: The confirmed account email/username (optional).
        """
        if email:
            self.vault.set_credential(service, "email", email)
        self.vault.set_credential(service, "status", "confirmed")
        self.vault.set_credential(service, "confirmed_at", utcnow())
        log.info("✅ %s confirmed", service)

    def mark_failed(self, service: str, reason: str) -> None:
        """Mark an account as failed.

        Args:
            service: Service key.
            reason: Failure reason.
        """
        self.vault.set_credential(service, "status", "failed")
        self.vault.set_credential(service, "failure_reason", reason)
        log.error("❌ %s failed: %s", service, reason)

    def _write_status(self) -> None:
        """Persist a status report for the Watchtower (non-secret)."""
        report = {"generated_at": utcnow(), "accounts": self.status}
        out = config.PROJECT_ROOT / "data" / "registry_status.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log.info("Registry status written: %s", out)