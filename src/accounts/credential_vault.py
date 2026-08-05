"""Encrypted credential vault for OracleForge Studios.

All secrets (usernames, passwords, API keys) are encrypted at rest using
``cryptography.Fernet``. The encryption key is derived from a master password
via PBKDF2-HMAC-SHA256 with a random salt.

Files:
    data/vault/credentials.enc   — the encrypted vault (never plaintext)

Security model:
- Master password is never stored. Only the salt + encrypted blobs exist on disk.
- Decrypted secrets live only in memory for the duration of an unlocked session.
- Export produces an encrypted portable backup (Fernet token) with its own
  random salt, decryptable with the master password.
- Nothing secret is ever written to logs.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .. import config
from ..logger import get_logger

log = get_logger("credential_vault")

#: Vault format version
VAULT_VERSION = 1

#: PBKDF2 iteration count (OWASP recommended)
ITERATIONS = 600_000


def _vault_path() -> Path:
    """Resolve the vault file path.

    Returns:
        Path to ``data/vault/credentials.enc`` (parent dirs created).
    """
    raw = config.env("VAULT_PATH", "data/vault/credentials.enc")
    path = Path(raw)
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _derive_key(master_password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from the master password.

    Args:
        master_password: Master password string.
        salt: 16-byte random salt.

    Returns:
        URL-safe Fernet key bytes.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))


def _now() -> str:
    """Current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CredentialVault:
    """Encrypted credential store.

    Typical usage::

        vault = CredentialVault()
        vault.initialize(master_password="hunter2-secure")
        vault.set_credential("twitter", "api_key", "sk-...")
        api_key = vault.get_credential("twitter", "api_key")
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        """Initialize the vault object.

        Args:
            path: Optional explicit vault file path (defaults to env).
        """
        self.path = path or _vault_path()
        self._fernet: Optional[Fernet] = None
        self._data: Dict[str, Any] = {}
        self._salt: bytes = b""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        """Check whether a vault file exists.

        Returns:
            True if the vault file is present.
        """
        return self.path.exists()

    def initialize(self, master_password: str) -> None:
        """Create a brand-new empty vault.

        Args:
            master_password: Master password used to encrypt everything.

        Raises:
            ValueError if the vault already exists.
        """
        if self.exists():
            raise ValueError("Vault already exists — use unlock() instead")
        self._salt = os.urandom(16)
        self._fernet = Fernet(_derive_key(master_password, self._salt))
        self._data = {
            "version": VAULT_VERSION,
            "created_at": _now(),
            "services": {},
        }
        self._persist()
        log.info("Credential vault initialized at %s", self.path)

    def unlock(self, master_password: str) -> bool:
        """Decrypt and load the vault.

        Args:
            master_password: Master password.

        Returns:
            True on success, False on wrong password/corrupt file.
        """
        if not self.exists():
            log.error("Vault not found: %s", self.path)
            return False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._salt = base64.b64decode(raw["salt"])
            token = raw["payload"].encode("utf-8")
            self._fernet = Fernet(_derive_key(master_password, self._salt))
            plaintext = self._fernet.decrypt(token)
            self._data = json.loads(plaintext.decode("utf-8"))
            log.info("Credential vault unlocked")
            return True
        except Exception as exc:  # noqa: BLE001 — wrong password or corruption
            self._fernet = None
            self._data = {}
            log.error("Vault unlock failed: %s", exc)
            return False

    def lock(self) -> None:
        """Wipe the in-memory decrypted data."""
        self._fernet = None
        self._data = {}
        log.info("Credential vault locked")

    @property
    def unlocked(self) -> bool:
        """Whether the vault is currently unlocked in memory."""
        return self._fernet is not None

    # ------------------------------------------------------------------
    # Credential access
    # ------------------------------------------------------------------

    def set_credential(self, service: str, key: str, value: str) -> None:
        """Store a secret for a service.

        Args:
            service: Service name (e.g. "twitter", "openai").
            key: Credential key (e.g. "api_key", "password").
            value: Secret value.

        Raises:
            RuntimeError if the vault is locked.
        """
        self._require_unlocked()
        services = self._data.setdefault("services", {})
        service_data = services.setdefault(service.lower(), {})
        service_data[key] = value
        self._data["updated_at"] = _now()
        self._persist()

    def get_credential(self, service: str, key: str, default: str = "") -> str:
        """Read a secret.

        Args:
            service: Service name.
            key: Credential key.
            default: Fallback if missing.

        Returns:
            The secret value.
        """
        self._require_unlocked()
        return self._data.get("services", {}).get(service.lower(), {}).get(key, default)

    def get_service_credentials(self, service: str) -> Dict[str, str]:
        """Return all credentials for a service.

        Args:
            service: Service name.

        Returns:
            Dict of key -> secret.
        """
        self._require_unlocked()
        return dict(self._data.get("services", {}).get(service.lower(), {}))

    def list_services(self) -> List[str]:
        """List services stored in the vault.

        Returns:
            Sorted list of service names.
        """
        self._require_unlocked()
        return sorted(self._data.get("services", {}).keys())

    def delete_service(self, service: str) -> None:
        """Delete a service and all its credentials.

        Args:
            service: Service name.
        """
        self._require_unlocked()
        self._data.get("services", {}).pop(service.lower(), None)
        self._persist()

    # ------------------------------------------------------------------
    # Backup / restore
    # ------------------------------------------------------------------

    def export_backup(self) -> bytes:
        """Export an encrypted backup (portable Fernet token).

        Returns:
            Opaque bytes — decryptable with the same master password.
        """
        self._require_unlocked()
        assert self._fernet is not None
        payload = json.dumps(self._data, default=str).encode("utf-8")
        return self._fernet.encrypt(payload)

    def write_backup(self, out_path: Path) -> Path:
        """Write an encrypted backup to disk.

        Args:
            out_path: Destination path.

        Returns:
            Path to the backup file.
        """
        token = self.export_backup()
        payload = {
            "version": VAULT_VERSION,
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "backup_of": str(self.path),
            "created_at": _now(),
            "payload": token.decode("utf-8"),
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("Encrypted backup written: %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_unlocked(self) -> None:
        """Raise if the vault is not unlocked."""
        if self._fernet is None:
            raise RuntimeError("Vault is locked — unlock with master password first")

    def _persist(self) -> None:
        """Encrypt in-memory data and write to disk."""
        assert self._fernet is not None
        payload = json.dumps(self._data, default=str).encode("utf-8")
        token = self._fernet.encrypt(payload)
        data = {
            "version": VAULT_VERSION,
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "created_at": self._data.get("created_at", _now()),
            "updated_at": self._data.get("updated_at", _now()),
            "payload": token.decode("utf-8"),
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")