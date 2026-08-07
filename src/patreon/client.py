"""Patreon API client for OracleForge Studios.

Wraps the official ``patreon`` library to fetch patron/member details and
refresh the access token. All secrets come from environment variables.

Note: The ``patreon`` library is OAuth2-based. For the webhook flow we use
``PATREON_ACCESS_TOKEN`` (a creator token). The client exposes both a
lightweight REST helper (via ``requests``) and a wrapper for the official
library's JSON-API structures, since the official package may lag on the
current API shape.
"""

from __future__ import annotations

import requests
from typing import Any, Dict, Optional

from .. import config
from ..logger import get_logger

log = get_logger("patreon_client")

#: Patreon API base URL
PATREON_API = "https://www.patreon.com/api/oauth2/v2"


def has_credentials() -> bool:
    """Check whether Patreon credentials are configured.

    Returns:
        True if the access token is set.
    """
    return bool(config.env("PATREON_ACCESS_TOKEN"))


def _headers() -> Dict[str, str]:
    """Build authenticated request headers.

    Returns:
        Headers dict with the bearer token.
    """
    return {
        "Authorization": f"Bearer {config.env('PATREON_ACCESS_TOKEN')}",
        "Content-Type": "application/json",
    }


def get_patron(patreon_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single patron/member by Patreon ID.

    Args:
        patreon_id: The Patreon member ID.

    Returns:
        Normalized patron dict: {email, tier, tier_level, status, full_name}
        or None on failure.
    """
    if not has_credentials():
        log.warning("Patreon not configured — cannot fetch patron %s", patreon_id)
        return None

    url = f"{PATREON_API}/members/{patreon_id}"
    params = {
        "include": "currently_entitled_tiers,user",
        "fields[member]": "full_name,email,patron_status,last_charge_date,pledge_relation_start",
        "fields[tier]": "title,amount_cents",
        "fields[user]": "email,full_name",
    }
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return _normalize_member(resp.json())
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to fetch Patreon patron %s: %s", patreon_id, exc)
        return None


def list_patrons() -> list:
    """Fetch all patrons (first page).

    Returns:
        List of normalized patron dicts.
    """
    if not has_credentials():
        return []
    url = f"{PATREON_API}/members"
    params = {
        "page[size]": "25",
        "include": "currently_entitled_tiers,user",
        "fields[member]": "full_name,email,patron_status,last_charge_date",
        "fields[tier]": "title",
        "fields[user]": "email,full_name",
    }
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return _normalize_members(resp.json())
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to fetch Patreon patrons: %s", exc)
        return []


def _normalize_members(payload: Dict[str, Any]) -> list:
    """Normalize a JSON:API member list.

    Args:
        payload: Patreon API response.

    Returns:
        List of normalized patron dicts.
    """
    data = payload.get("data", [])
    included = payload.get("included", [])
    users = {r["id"]: r for r in included if r.get("type") == "user"}
    tiers = {r["id"]: r for r in included if r.get("type") == "tier"}

    patrons = []
    for member in data:
        patrons.append(_build_patron(member, users, tiers))
    return patrons


def _normalize_member(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a single-member JSON:API response.

    Args:
        payload: Patreon API response.

    Returns:
        Normalized patron dict or None.
    """
    data = payload.get("data")
    if not data:
        return None
    included = payload.get("included", [])
    users = {r["id"]: r for r in included if r.get("type") == "user"}
    tiers = {r["id"]: r for r in included if r.get("type") == "tier"}
    return _build_patron(data, users, tiers)


def _build_patron(member: Dict[str, Any], users: Dict[str, Any],
                  tiers: Dict[str, Any]) -> Dict[str, Any]:
    """Build a normalized patron dict from JSON:API members.

    Args:
        member: Member resource.
        users: Included user resources by id.
        tiers: Included tier resources by id.

    Returns:
        Normalized patron dict.
    """
    attrs = member.get("attributes", {})
    relationships = member.get("relationships", {})

    # Resolve tier from currently_entitled_tiers relationship
    tier_title = ""
    tier_rels = relationships.get("currently_entitled_tiers", {}).get("data", [])
    if tier_rels:
        tier_id = tier_rels[0].get("id")
        tier_title = tiers.get(tier_id, {}).get("attributes", {}).get("title", "")

    # Resolve user email
    email = attrs.get("email", "")
    user_rel = relationships.get("user", {}).get("data", {})
    if user_rel:
        user_attrs = users.get(user_rel.get("id"), {}).get("attributes", {})
        email = email or user_attrs.get("email", "")

    # Internal module import to avoid circular dependency at package init
    from .tiers import tier_by_name
    tier_level = tier_by_name(tier_title)

    return {
        "patreon_id": member.get("id"),
        "email": email,
        "full_name": attrs.get("full_name", ""),
        "tier": tier_title,
        "tier_level": tier_level,
        "status": attrs.get("patron_status", "unknown"),
    }