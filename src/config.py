"""Central configuration loader for OracleForge.

Loads environment variables from ``.env`` (via python-dotenv), YAML
config files (prompts, schedule), and provides typed accessors plus a
:func:`validate` helper that reports which optional/required keys are set.

Everything that needs configuration should import from this module so that
API keys never get hardcoded anywhere else in the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Project root = parent of the src/ directory (OracleForge/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
WEB_DIR = PROJECT_ROOT / "web"

# Load the .env file if it exists (safe no-op otherwise).
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------

def env(key: str, default: str = "") -> str:
    """Return an environment variable as a string.

    Args:
        key: Environment variable name.
        default: Fallback value if unset/empty.

    Returns:
        The string value of the variable (or default).
    """
    return os.getenv(key, default).strip()


def env_int(key: str, default: int = 0) -> int:
    """Return an environment variable as an integer.

    Args:
        key: Environment variable name.
        default: Fallback integer if unset or unparsable.

    Returns:
        Parsed integer value.
    """
    raw = env(key, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def env_bool(key: str, default: bool = False) -> bool:
    """Return an environment variable as a boolean.

    Accepts: "1", "true", "yes", "on" (case-insensitive) as True.

    Args:
        key: Environment variable name.
        default: Fallback boolean if unset.

    Returns:
        Boolean interpretation of the value.
    """
    raw = env(key, "").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def env_list(key: str, default: Optional[List[str]] = None) -> List[str]:
    """Return an environment variable as a comma-separated list.

    Args:
        key: Environment variable name.
        default: Fallback list if unset/empty.

    Returns:
        List of trimmed, non-empty items.
    """
    raw = env(key, "")
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# YAML configs
# ---------------------------------------------------------------------------

def load_yaml(filename: str) -> Dict[str, Any]:
    """Load a YAML file from the config directory.

    Args:
        filename: Name of the YAML file (e.g. "prompts.yaml").

    Returns:
        Parsed dict. Raises FileNotFoundError/ValueError on problems.
    """
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


# ---------------------------------------------------------------------------
# Convenience accessors for common config
# ---------------------------------------------------------------------------

def prompts() -> Dict[str, str]:
    """Return the prompt templates from ``config/prompts.yaml``.

    Returns:
        Dict mapping template name -> formatted prompt text.
    """
    return load_yaml("prompts.yaml")


def schedule() -> Dict[str, Any]:
    """Return the orchestration schedule from ``config/schedule.yaml``.

    Returns:
        Dict of schedule blocks (cron strings, job lists, params).
    """
    return load_yaml("schedule.yaml")


def get(key: str, default: str = "") -> str:
    """Alias for :func:`env` — generic getter for any setting.

    Args:
        key: Environment variable name.
        default: Fallback string.

    Returns:
        String value.
    """
    return env(key, default)


# ---------------------------------------------------------------------------
# Key sets
# ---------------------------------------------------------------------------

#: Integration API keys (existence determines whether a feature is enabled)
INTEGRATION_KEYS = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_SECRET",
    "TWITTER_BEARER_TOKEN",
    "DISCORD_BOT_TOKEN",
    "LINKEDIN_ACCESS_TOKEN",
    "STRIPE_SECRET_KEY",
]

#: Core required keys for the system to boot
REQUIRED_KEYS = ["FLASK_SECRET_KEY"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate() -> Dict[str, bool]:
    """Check which API keys / required settings are present.

    This does NOT fail the app — missing optional keys simply disable the
    corresponding feature (e.g. no OpenAI key -> SVG image fallback).

    Returns:
        Dict mapping key name -> whether it is set.
    """
    status: Dict[str, bool] = {}
    for key in REQUIRED_KEYS + INTEGRATION_KEYS:
        status[key] = bool(env(key))
    return status


def summary() -> str:
    """Human-readable summary of the configuration status.

    Returns:
        Multi-line string describing which integrations are active.
    """
    status = validate()
    lines = ["OracleForge configuration status:"]
    for key in REQUIRED_KEYS + INTEGRATION_KEYS:
        marker = "✅" if status[key] else "❌"
        lines.append(f"  {marker} {key}")
    return "\n".join(lines)