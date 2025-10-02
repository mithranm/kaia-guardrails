from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class HookError(Exception):
    """Raised when a hook fails in a way the orchestrator should record."""


@dataclass
class HookBase:
    """Minimal hook contract.

    Subclasses should implement `run(self, context: Dict[str, Any]) -> Any`.
    """

    name: str
    priority: int = 100
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=lambda: ["PreToolUse", "PostToolUse", "UserPromptSubmit"])  # Which events this hook handles

    def run(self, context: dict[str, Any]) -> Any | None:
        """Execute the hook.

        Args:
            context: mutable dict that represents the workflow context.

        Returns:
            Any optional result. If an exception occurs, raise HookError.
        """

        raise NotImplementedError("Hook must implement run(context)")
