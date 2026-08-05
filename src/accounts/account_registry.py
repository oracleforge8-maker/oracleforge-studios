"""Account registry — defines all accounts and generates secure credentials.

Defines which services OracleForge Studios needs, generates strong unique
passwords/API keys for each, and persists generated metadata (usernames) into
the encrypted vault via the orchestrator.

Security: generated secrets live only in the vault after encryption — never in
plaintext config files.
"""

from __future__ import annotations

import secrets
import string
from typing import Any, Dict, List

from ..logger import get_logger

log = get_logger("account_registry")

#: Account definitions: service key -> signup metadata
ACCOUNT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "service": "gmail",
        "signup_url": "https://accounts.google.com/signup",
        "human_required": True,          # Google ToS + phone verification
        "fields": ["username", "password", "recovery_email"],
        "notes": "Master identity. Used for all service registrations.",
    },
    "twitter": {
        "service": "twitter",
        "signup_url": "https://x.com/i/flow/signup",
        "human_required": True,          # email/phone verification + CAPTCHA
        "fields": ["username", "password", "email", "phone"],
        "bio": "AI-powered intelligence agent tracking the memecoin revolution. Built by OracleForge.",
        "notes": "Primary bot account (@ChadSatoshi). Bio set on profile.",
    },
    "discord": {
        "service": "discord",
        "signup_url": "https://discord.com/register",
        "human_required": True,          # CAPTCHA / email verification
        "fields": ["username", "password", "email"],
        "channels": ["announcements", "trend-radar", "alpha-chat", "memes", "subscriber-only"],
        "notes": "Server with 5 channels; bot token added post-registration.",
    },
    "linkedin": {
        "service": "linkedin",
        "signup_url": "https://www.linkedin.com/signup",
        "human_required": True,          # CAPTCHA / email verification
        "fields": ["username", "password", "email"],
        "notes": "Professional B2B profile for The Forge outreach.",
    },
    "openai": {
        "service": "openai",
        "signup_url": "https://platform.openai.com/signup",
        "human_required": True,          # phone verification required
        "fields": ["username", "password", "email", "phone"],
        "notes": "DALL-E 3 access. API key generated after login.",
    },
    "stripe": {
        "service": "stripe",
        "signup_url": "https://dashboard.stripe.com/register",
        "human_required": True,          # business details / payment method
        "fields": ["username", "password", "email"],
        "notes": "Test mode initially. Publishable + secret keys captured.",
    },
    "namecheap": {
        "service": "namecheap",
        "signup_url": "https://www.namecheap.com/myaccount/signup/",
        "human_required": True,          # email verification
        "fields": ["username", "password", "email"],
        "notes": "For oracleforge.ai domain purchase.",
    },
}


def generate_password(length: int = 24) -> str:
    """Generate a strong random password.

    Args:
        length: Desired length (default 24).

    Returns:
        Password containing upper, lower, digits, and symbols.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    # Guarantee at least one of each class
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def generate_username(prefix: str) -> str:
    """Generate a unique-ish username for a service.

    Args:
        prefix: Service-specific prefix (e.g. "oracleforge").

    Returns:
        Lowercase username with random suffix.
    """
    suffix = secrets.token_hex(4)  # 8 hex chars
    return f"{prefix}.{suffix}"


def generate_api_key(bits: int = 256) -> str:
    """Generate a hex API key.

    Args:
        bits: Entropy in bits (default 256).

    Returns:
        Hex string key.
    """
    return secrets.token_hex(bits // 8)


def build_generated_credentials() -> Dict[str, Dict[str, str]]:
    """Generate placeholder credentials for every account.

    The orchestrator uses these to pre-fill signup forms, then stores the
    FINAL confirmed credentials after the human completes verification.

    Returns:
        Dict: service -> {field: generated-value}
    """
    generated: Dict[str, Dict[str, str]] = {}
    for service, definition in ACCOUNT_DEFINITIONS.items():
        creds: Dict[str, str] = {}
        for field in definition["fields"]:
            if field == "password":
                creds[field] = generate_password()
            elif field == "username":
                creds[field] = generate_username(f"of.{service}")
            elif field == "email":
                # Placeholder — real email comes from the Gmail account
                creds[field] = ""
            elif field == "recovery_email":
                creds[field] = ""
            elif field == "phone":
                creds[field] = ""  # human must provide
            else:
                creds[field] = ""
        generated[service] = creds
    return generated


def account_urls() -> Dict[str, str]:
    """Return the signup/login URLs for every account.

    Returns:
        Dict: service -> signup URL.
    """
    return {name: definition["signup_url"] for name, definition in ACCOUNT_DEFINITIONS.items()}