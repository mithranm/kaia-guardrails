"""Focus tracking and management."""

import os
import sys
from pathlib import Path

from ..base import HookBase


class FocusTrackerHook(HookBase):
    """Displays current focus from .claude/current-focus.txt."""

    def __init__(self):
        super().__init__(name="focus_tracker", priority=10)

    def run(self, context: dict) -> dict:
        """Display current focus to user."""
        project_root = Path(context.get("project_root", Path.cwd()))
        focus_file = project_root / ".claude" / "current-focus.txt"

        # Only show on UserPromptSubmit (not every tool use)
        hook_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")
        if hook_event != "UserPromptSubmit":
            return {"status": "skipped", "reason": "not UserPromptSubmit"}

        if not focus_file.exists():
            print("📍 No current focus set (create .claude/current-focus.txt)", file=sys.stderr)
            return {"status": "warning", "focus": None}

        # Read and display focus
        with open(focus_file) as f:
            focus = f.read().strip()

        if focus:
            print(f"📍 Current Focus: {focus}", file=sys.stderr)
            return {"status": "success", "focus": focus}
        else:
            print("📍 Current focus file is empty", file=sys.stderr)
            return {"status": "warning", "focus": None}
