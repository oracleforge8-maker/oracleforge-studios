"""Credential manifest delivery.

Generates a complete, ENCRYPTED manifest containing:
- All usernames/passwords (from the vault, encrypted)
- All API keys (from the vault, encrypted)
- All account URLs (Twitter, Discord invite, LinkedIn, Stripe, etc.)
- Admin access links

The manifest is a self-contained Fernet-encrypted JSON blob that can be
decrypted with the master password. It is written to
``data/vault/manifest.enc`` and can be exported for backup.

Security: the manifest never contains plaintext secrets — only the encrypted
payload. Decryption requires the master password.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from .. import config
from ..logger import get_logger
from . import account_registry as registry
from . import credential_vault

log = get_logger("manifest")

#: Manifest format version
MANIFEST_VERSION = 1


def _manifest_path() -> Path:
    """Resolve the manifest file path.

    Returns:
        Path to ``data/vault/manifest.enc``.
    """
    raw = config.env("MANIFEST_PATH", "data/vault/manifest.enc")
    path = Path(raw)
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_manifest(vault: credential_vault.CredentialVault,
                   master_password: str) -> Dict[str, Any]:
    """Build the full manifest payload (encrypted).

    Args:
        vault: Unlocked CredentialVault.
        master_password: Master password (used to derive the manifest key).

    Returns:
        Dict with "version", "salt", "payload" (Fernet token).
    """
    if not vault.unlocked:
        raise RuntimeError("Vault must be unlocked to build a manifest")

    # Collect all service credentials (decrypted in memory only)
    services: Dict[str, Dict[str, str]] = {}
    for service in vault.list_services():
        services[service] = vault.get_service_credentials(service)

    # Account URLs
    urls = registry.account_urls()

    # Admin access links (dashboard + vault)
    site_url = config.env("SITE_URL", "http://localhost:5000")
    admin_links = {
        "dashboard": f"{site_url}/dashboard",
        "vault": f"{site_url}/dashboard/vault",
        "health": f"{site_url}/dashboard/health",
    }

    payload = {
        "generated_at": _now(),
        "studio": "OracleForge Studios",
        "services": services,
        "account_urls": urls,
        "admin_links": admin_links,
        "notes": (
            "Decrypt with the master password. Never share this file or the "
            "master password. Rotate credentials if this manifest is exposed."
        ),
    }

    # Encrypt with a fresh key derived from the master password
    salt = __import__("os").urandom(16)
    key = credential_vault._derive_key(master_password, salt)  # noqa: SLF001
    fernet = Fernet(key)
    token = fernet.encrypt(json.dumps(payload, default=str).encode("utf-8"))

    return {
        "version": MANIFEST_VERSION,
        "salt": base64.b64encode(salt).decode("ascii"),
        "created_at": _now(),
        "payload": token.decode("utf-8"),
    }


def write_manifest(vault: credential_vault.CredentialVault,
                   master_password: str,
                   out_path: Optional[Path] = None) -> Path:
    """Write the encrypted manifest to disk.

    Args:
        vault: Unlocked CredentialVault.
        master_password: Master password.
        out_path: Optional output path (defaults to data/vault/manifest.enc).

    Returns:
        Path to the written manifest.
    """
    manifest = build_manifest(vault, master_password)
    path = out_path or _manifest_path()
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Encrypted manifest written: %s", path)
    return path


def decrypt_manifest(manifest_path: Path, master_password: str) -> Dict[str, Any]:
    """Decrypt a manifest file.

    Args:
        manifest_path: Path to the .enc manifest.
        master_password: Master password.

    Returns:
        The decrypted manifest dict.

    Raises:
        ValueError on wrong password or corrupt file.
    """
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    salt = base64.b64decode(raw["salt"])
    key = credential_vault._derive_key(master_password, salt)  # noqa: SLF001
    fernet = Fernet(key)
    try:
        plaintext = fernet.decrypt(raw["payload"].encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Wrong master password or corrupt manifest") from exc
    return json.loads(plaintext.decode("utf-8"))