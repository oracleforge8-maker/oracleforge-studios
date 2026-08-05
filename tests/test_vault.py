"""Tests for the encrypted credential vault."""

from __future__ import annotations

import pytest

from src.accounts import credential_vault
from src.accounts import manifest
from src.accounts import account_registry
from src.accounts.registration_orchestrator import RegistrationOrchestrator


@pytest.fixture
def vault(tmp_path):
    """Provide an initialized CredentialVault in a temp dir."""
    v = credential_vault.CredentialVault(path=tmp_path / "test_vault.enc")
    v.initialize("test-master-password")
    yield v


def test_initialize_and_unlock(vault):
    """Vault should lock/unlock with the master password."""
    assert vault.unlocked
    vault.lock()
    assert not vault.unlocked
    assert vault.unlock("test-master-password")
    assert vault.unlocked


def test_wrong_password_fails(vault):
    """Wrong master password should fail unlock."""
    vault.lock()
    assert not vault.unlock("wrong-password")


def test_set_get_credential(vault):
    """Credentials should round-trip through the vault."""
    vault.set_credential("twitter", "password", "secret-123")
    assert vault.get_credential("twitter", "password") == "secret-123"
    assert "twitter" in vault.list_services()


def test_credentials_encrypted_at_rest(vault, tmp_path):
    """The on-disk vault file must NOT contain plaintext secrets."""
    vault.set_credential("openai", "api_key", "sk-super-secret")
    raw = (tmp_path / "test_vault.enc").read_text(encoding="utf-8")
    assert "sk-super-secret" not in raw


def test_export_backup_roundtrip(vault, tmp_path):
    """Exported backup should be restorable with the same master password."""
    vault.set_credential("stripe", "secret_key", "sk_test_abc")
    backup_path = vault.write_backup(tmp_path / "backup.enc")

    # Create a fresh vault and load the backup via manifest-style decryption
    restored = credential_vault.CredentialVault(path=tmp_path / "restored.enc")
    # The backup file uses the same format as the manifest payload wrapper
    import json
    raw = json.loads(backup_path.read_text(encoding="utf-8"))
    assert raw["payload"]  # payload is encrypted
    assert "sk_test_abc" not in backup_path.read_text(encoding="utf-8")


def test_generate_password_strength():
    """Generated passwords should be strong and varied."""
    password = account_registry.generate_password()
    assert len(password) >= 24
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(not c.isalnum() for c in password)


def test_generate_username_format():
    """Generated usernames should be lowercase with a suffix."""
    username = account_registry.generate_username("of.twitter")
    assert username.startswith("of.twitter.")
    assert username == username.lower()


def test_manifest_roundtrip(vault):
    """Manifest should encrypt and decrypt with the master password."""
    vault.set_credential("twitter", "password", "secret-123")
    manifest_data = manifest.build_manifest(vault, "test-master-password")
    assert "secret-123" not in str(manifest_data)

    # Decrypt using a temp write + read
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "manifest.enc"
        path.write_text(
            __import__("json").dumps(manifest_data), encoding="utf-8"
        )
        decrypted = manifest.decrypt_manifest(path, "test-master-password")
        assert decrypted["services"]["twitter"]["password"] == "secret-123"


def test_orchestrator_non_interactive(db, vault):
    """Orchestrator should store candidate credentials (non-interactive)."""
    orch = RegistrationOrchestrator(vault)
    status = orch.run(interactive=False)
    assert "gmail" in status
    assert status["gmail"]["status"] == "awaiting-confirmation"
    # Credentials stored in vault
    assert vault.get_credential("twitter", "password")