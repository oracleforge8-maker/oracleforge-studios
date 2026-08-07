"""Patreon tier definitions and mapping for OracleForge Studios.

Tiers:
- Tier 1 — Forge Supporter: early trend reports
- Tier 2 — Meme Master: weekly PDF reports + Discord access
- Tier 3 — Forge Master: everything + custom analysis

Tier names are matched against Patreon's tier titles (case-insensitive,
fuzzy). The mapping is configurable via env vars:
    PATREON_TIER1_NAME / PATREON_TIER2_NAME / PATREON_TIER3_NAME
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .. import config

#: Tier definitions: level -> metadata
TIERS: Dict[int, Dict[str, object]] = {
    1: {
        "name": "Forge Supporter",
        "level": 1,
        "benefits": ["Early trend reports"],
        "description": "Access to early trend reports",
    },
    2: {
        "name": "Meme Master",
        "level": 2,
        "benefits": ["Weekly PDF reports", "Discord access"],
        "description": "Weekly PDF reports + Discord access",
    },
    3: {
        "name": "Forge Master",
        "level": 3,
        "benefits": ["Everything", "Custom analysis"],
        "description": "Everything + custom analysis",
    },
}


def tier_names() -> Dict[int, str]:
    """Return the configured tier names (overridable via env).

    Returns:
        Dict: level -> tier name.
    """
    return {
        1: config.env("PATREON_TIER1_NAME", "Forge Supporter"),
        2: config.env("PATREON_TIER2_NAME", "Meme Master"),
        3: config.env("PATREON_TIER3_NAME", "Forge Master"),
    }


def tier_by_name(name: str) -> Optional[int]:
    """Map a Patreon tier title to a tier level.

    Args:
        name: Patreon tier title (e.g. "Meme Master").

    Returns:
        Tier level (1-3) or None if unknown.
    """
    if not name:
        return None
    normalized = name.strip().lower()
    for level, configured in tier_names().items():
        if normalized == configured.lower():
            return level
    # Fuzzy fallback: match on distinctive keywords.
    # Check "meme master" BEFORE the generic "master" so "Meme Master Tier"
    # maps to tier 2, not tier 3.
    if "meme master" in normalized:
        return 2
    if "forge master" in normalized or "master" in normalized:
        return 3
    if "meme" in normalized:
        return 2
    if "supporter" in normalized or "forge" in normalized:
        return 1
    return None


def tier_info(level: int) -> Dict[str, object]:
    """Return tier metadata for a level.

    Args:
        level: Tier level (1-3).

    Returns:
        Tier dict (falls back to level 1 for unknown levels).
    """
    return TIERS.get(level, TIERS[1])


def all_tiers() -> List[Dict[str, object]]:
    """Return all tier definitions.

    Returns:
        List of tier dicts sorted by level.
    """
    return [TIERS[level] for level in sorted(TIERS)]