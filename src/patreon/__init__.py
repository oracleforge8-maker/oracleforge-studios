"""OracleForge Studios — Patreon integration.

Handles Patreon webhooks, patron data sync, tier tracking, and content
delivery based on membership tier.

Modules:
- ``tiers``   — tier definitions and mapping (Forge Supporter / Meme Master / Forge Master)
- ``client``  — Patreon API client (fetch patron details, refresh tokens)
- ``webhook`` — webhook receiver with signature verification

All secrets come from environment variables (never hardcoded).
"""