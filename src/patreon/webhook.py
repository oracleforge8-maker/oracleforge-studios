"""Patreon webhook receiver with signature verification.

Patreon signs webhook payloads with an HMAC-SHA1 digest of the raw request
body, using the webhook secret. The digest is sent in the
``X-Patreon-Signature`` header.

This module:
1. Verifies the signature (constant-time compare).
2. Parses the event type (members:create / members:update / members:delete).
3. Extracts the member ID and calls the Patreon API to fetch full details.
4. Returns a normalized event dict for the caller to persist.

Security: the webhook secret comes from ``PATREON_WEBHOOK_SECRET`` env var.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, Optional

from .. import config
from ..logger import get_logger
from . import client as patreon_client

log = get_logger("patreon_webhook")

#: Supported event types
EVENT_TYPES = {"members:create", "members:update", "members:delete"}


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify the Patreon webhook signature.

    Args:
        payload: Raw request body bytes.
        signature: Value of the X-Patreon-Signature header.

    Returns:
        True if the signature is valid.
    """
    secret = config.env("PATREON_WEBHOOK_SECRET")
    if not secret:
        log.error("PATREON_WEBHOOK_SECRET not configured")
        return False
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_event(payload: bytes) -> Optional[Dict[str, Any]]:
    """Parse a verified Patreon webhook payload.

    Args:
        payload: Raw request body bytes.

    Returns:
        Dict: {"event": str, "member_id": str, "patron": dict|None}
        or None if the payload is malformed.
    """
    import json
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.error("Invalid Patreon webhook payload: %s", exc)
        return None

    event = data.get("data", {}).get("type", "")
    if event not in EVENT_TYPES:
        log.warning("Unsupported Patreon event type: %s", event)
        return None

    member_id = data.get("data", {}).get("id", "")
    if not member_id:
        log.error("Patreon webhook missing member id")
        return None

    # Fetch full patron details from the API
    patron = patreon_client.get_patron(member_id)

    return {
        "event": event,
        "member_id": member_id,
        "patron": patron,
    }