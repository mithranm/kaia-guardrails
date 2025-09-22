"""kaia_guardrails.hooks package - adapters for existing .claude hooks and orchestrator.

This package provides:
- HookBase: minimal contract for hooks
- loader: discovery of bundled and external hooks
- orchestrator: single entrypoint that runs configured workflows

The actual hook implementations currently live in the repository at
`.claude/hooks/`. To avoid duplicating code, lightweight wrapper modules
in this package dynamically import those files and re-export symbols.
"""

from .base import HookBase, HookError
from .loader import discover_hooks, load_hook_by_name
from .orchestrator import Orchestrator

__all__ = [
    "HookBase",
    "HookError",
    "discover_hooks",
    "load_hook_by_name",
    "Orchestrator",
]
