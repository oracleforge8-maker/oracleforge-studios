"""OracleForge Studios accounts package.

Tools for identity management:
- ``credential_vault``        — encrypted at-rest credential storage
- ``account_registry``        — account definitions & secure credential generation
- ``gmail_creator``           — browser-driven Gmail onboarding (human-verified)
- ``registration_orchestrator`` — multi-service registration flow
- ``manifest``                — encrypted credential manifest delivery

Security model:
- Secrets are encrypted with cryptography.Fernet using a key derived
  from the master password via PBKDF2-HMAC-SHA256.
- Nothing is ever written to disk unencrypted.
- Passwords/API keys are never logged.
"""