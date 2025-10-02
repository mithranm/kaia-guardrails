"""Simple focus tracking from AGENTS.md."""

import os
import re
import sys
from pathlib import Path

from ..base import HookBase


class FocusTrackerHook(HookBase):
    """Tracks current focus from AGENTS.md and reminds user."""

    def __init__(self):
        super().__init__(name="focus_tracker", priority=10)

    def run(self, context: dict) -> dict:
        """Extract and display current focus from AGENTS.md."""
        project_root = Path(context.get("project_root", Path.cwd()))
        agents_file = project_root / "AGENTS.instructions.md"

        if not agents_file.exists():
            return {"status": "skipped", "reason": "no AGENTS.instructions.md"}

        # Extract focus from AGENTS.md
        with open(agents_file) as f:
            content = f.read()

        # Look for "Current Focus:" or "**Current Focus**:" pattern
        focus_match = re.search(
            r"\*?\*?Current Focus\*?\*?:?\s*(.+?)(?:\n\n|$)", content, re.IGNORECASE | re.DOTALL
        )

        if focus_match:
            focus = focus_match.group(1).strip()
            # Limit to first line if multiline
            focus = focus.split("\n")[0].strip()

            # Only show on UserPromptSubmit (not every tool use)
            hook_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")
            if hook_event == "UserPromptSubmit":
                print(f"📍 Current Focus: {focus}", file=sys.stderr)

            return {"status": "success", "focus": focus}

        return {"status": "success", "focus": "No focus defined"}
