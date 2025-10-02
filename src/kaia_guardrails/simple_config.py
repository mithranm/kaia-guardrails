"""Simple configuration loading from .claude/settings.local.json."""

import json
import os
from pathlib import Path


def get_config(key: str, default: str | None = None) -> str | None:
    """Get config value from environment or settings.local.json.

    Args:
        key: Config key (e.g., "KAIA_JUDGE_LLM_URL")
        default: Default value if not found

    Returns:
        Config value or default
    """
    # Try environment variable first
    value = os.environ.get(key)
    if value:
        return value

    # Try .claude/settings.local.json
    project_root = Path.cwd()
    settings_file = project_root / ".claude" / "settings.local.json"

    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)

            # Check env section
            if key in settings.get("env", {}):
                return settings["env"][key]

        except (json.JSONDecodeError, KeyError):
            pass

    return default
