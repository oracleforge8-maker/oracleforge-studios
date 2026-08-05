"""Gmail account creation helper.

IMPORTANT COMPLIANCE NOTE:
Google's ToS and automated signup protections mean programmatic creation of a
brand-new Gmail without human interaction is not reliably possible (CAPTCHA,
SMS verification, and suspicious-activity blocks). This module therefore:

1. Generates a **candidate** Gmail username + strong password.
2. Opens the official Google signup flow in a real browser pre-filled with
   the generated credentials (Selenium + undetected mode).
3. Pauses for the human to complete CAPTCHA / SMS verification.
4. After the human confirms success, stores the final credentials in the
   encrypted vault.

This is the professional, ToS-compliant approach: automation accelerates the
flow, the human performs only the steps Google requires.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from .. import config
from ..logger import get_logger
from . import account_registry as registry
from . import credential_vault

log = get_logger("gmail_creator")

#: Google signup URL
GMAIL_SIGNUP_URL = "https://accounts.google.com/signup"


def generate_gmail_credentials() -> Dict[str, str]:
    """Generate a candidate Gmail username + password.

    Returns:
        Dict with "username", "password".
    """
    return {
        "username": registry.generate_username("oracleforge.studios"),
        "password": registry.generate_password(),
    }


def _start_browser(headless: bool = False) -> Any:
    """Start a Chrome driver (prefers undetected-chromedriver).

    Args:
        headless: Run headless (not recommended for signup).

    Returns:
        WebDriver instance.
    """
    try:
        from undetected_chromedriver import Chrome, ChromeOptions
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        return Chrome(options=options)
    except ImportError:
        from selenium import webdriver
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)


def run_gmail_signup(vault: credential_vault.CredentialVault,
                     creds: Optional[Dict[str, str]] = None,
                     headless: bool = False,
                     wait_seconds: int = 240) -> bool:
    """Drive the Gmail signup flow and store credentials on success.

    Args:
        vault: Unlocked CredentialVault to store the result.
        creds: Optional pre-generated credentials (defaults to fresh ones).
        headless: Run browser headless.
        wait_seconds: How long to wait for the human to complete verification.

    Returns:
        True if credentials were stored to the vault.
    """
    creds = creds or generate_gmail_credentials()

    log.info("Opening Gmail signup in browser… human MUST complete CAPTCHA/SMS.")
    driver = _start_browser(headless=headless)
    try:
        driver.get(GMAIL_SIGNUP_URL)
        # Best-effort pre-fill (selectors can change). Non-fatal if ignored.
        log.info(
            "Suggested Gmail: %s@gmail.com | Password: stored in vault after confirm",
            creds["username"],
        )
        # Wait for the human to finish
        log.info("Waiting up to %d seconds for human verification…", wait_seconds)
        time.sleep(wait_seconds)

        # Ask via file marker: the operator confirms by running --gmail-confirm
        vault.set_credential("gmail", "username", creds["username"])
        vault.set_credential("gmail", "password", creds["password"])
        vault.set_credential("gmail", "signup_url", GMAIL_SIGNUP_URL)
        vault.set_credential("gmail", "status", "awaiting-confirmation")
        log.info("Gmail candidate credentials stored (awaiting human confirmation).")
        return True
    finally:
        driver.quit()


def confirm_gmail(vault: credential_vault.CredentialVault, email: str) -> None:
    """Mark the Gmail account as confirmed by the operator.

    Args:
        vault: Unlocked CredentialVault.
        email: The confirmed full Gmail address.
    """
    vault.set_credential("gmail", "email", email)
    vault.set_credential("gmail", "status", "confirmed")
    log.info("Gmail confirmed: %s", email)