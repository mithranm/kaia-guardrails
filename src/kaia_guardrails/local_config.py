"""
Local Development Configuration Loader

Node.js-style config override system. Loads production config from pyproject.toml
and overrides with dev.pyproject.toml when running locally.
"""
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError as e:
        raise ImportError(
            "kaia-guardrails requires Python 3.11+ or the 'tomli' package "
            "to parse pyproject.toml on Python 3.10. "
            f"Install tomli: pip install tomli"
        ) from e


class LocalConfigLoader:
    """Node.js-style config loader with dev overrides."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or self._find_project_root()
        self.prod_config_path = self.project_root / 'pyproject.toml'
        self.dev_config_path = self.project_root / 'dev.pyproject.toml'
        self.config = self._load_merged_config()

    def _find_project_root(self) -> Path:
        """Find project root (where pyproject.toml exists)."""
        current = Path.cwd()
        while current.parent != current:
            if (current / 'pyproject.toml').exists():
                return current
            current = current.parent
        return Path.cwd()

    def _load_merged_config(self) -> Dict[str, Any]:
        """Load production config and merge with dev overrides (Node.js style)."""
        try:
            # Load production config
            prod_config = {}
            if self.prod_config_path.exists():
                with open(self.prod_config_path, 'rb') as f:
                    prod_config = tomllib.load(f)

            # Load dev overrides if exists
            dev_config = {}
            if self.dev_config_path.exists():
                with open(self.dev_config_path, 'rb') as f:
                    dev_config = tomllib.load(f)
                print(f"[DEV-CONFIG] Using local development overrides from {self.dev_config_path.name}")

            # Merge configs (dev overrides prod)
            merged = self._deep_merge(prod_config, dev_config)
            return merged

        except Exception as e:
            print(f"[CONFIG-ERROR] Failed to load configs: {e}")
            return {}

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries (Node.js style config override)."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get_tool_config(self, tool: str) -> Dict[str, Any]:
        """Get configuration for a specific tool (vibelint, kaia_guardrails, etc.)."""
        return self.config.get('tool', {}).get(tool, {})

    def get_llm_config(self, tool: str = 'vibelint') -> Dict[str, Any]:
        """Get LLM configuration with dev overrides applied."""
        tool_config = self.get_tool_config(tool)

        # Return merged config with dev overrides
        return {
            'base_url': tool_config.get('llm_base_url', ''),
            'api_key': tool_config.get('llm_api_key', ''),
            'model': tool_config.get('llm_model', ''),
            'timeout': tool_config.get('timeout', 30),
            'max_retries': tool_config.get('max_retries', 2)
        }

    def is_dev_mode(self) -> bool:
        """Check if dev config exists (like Node.js checking for .env.local)."""
        return self.dev_config_path.exists()


# Global instance for easy access
_config_loader = None

def get_local_config() -> LocalConfigLoader:
    """Get the global local config loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = LocalConfigLoader()
    return _config_loader