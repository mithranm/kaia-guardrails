from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import HookError
from .loader import DiscoveredHook, discover_hooks

logger = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    """Orchestrator discovers and runs hooks in order.

    It accepts an optional hooks_dir which will be searched for filesystem hooks.
    """

    hooks_dir: str | None = None

    def list_hooks(self) -> list[DiscoveredHook]:
        return discover_hooks(hooks_dir=self.hooks_dir)

    def run_all(self, initial_context: dict | None = None) -> dict[str, Any]:
        """Run all discovered hooks sequentially.

        Returns a dict with run results for each hook.
        """
        import os

        ctx: dict = initial_context or {}
        results: dict[str, Any] = {}
        current_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")

        for d in self.list_hooks():
            hook = d.hook
            if not getattr(hook, "enabled", True):
                results[d.name] = {"status": "skipped", "reason": "disabled"}
                continue

            # Check if hook wants to run on this event
            hook_events = getattr(hook, "events", None)
            if hook_events and current_event and current_event not in hook_events:
                results[d.name] = {"status": "skipped", "reason": f"not for event {current_event}"}
                continue

            try:
                res = hook.run(ctx)
                results[d.name] = {"status": "ok", "result": res}
            except HookError as e:
                logger.exception("hook %s raised HookError", d.name)
                results[d.name] = {"status": "error", "error": str(e)}
            except Exception as e:
                logger.exception("hook %s crashed", d.name)
                results[d.name] = {"status": "crash", "error": str(e)}

        return {"context": ctx, "results": results}
