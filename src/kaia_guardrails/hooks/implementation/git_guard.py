"""Git operations safety guard."""

import os
import sys

from ..base import HookBase


class GitGuardHook(HookBase):
    """Prevents dangerous git operations."""

    def __init__(self):
        super().__init__(name="git_guard", priority=30)

    def run(self, context: dict) -> dict:
        """Check for dangerous git operations."""
        tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
        if tool_name != "Bash":
            return {"status": "skipped", "reason": "not a bash command"}

        # Get command from tool input
        tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
        if not tool_input or "git" not in tool_input.lower():
            return {"status": "skipped", "reason": "not a git command"}

        # Check for dangerous operations
        dangerous_patterns = [
            ("push --force", "Force push detected"),
            ("push -f", "Force push detected"),
            ("reset --hard", "Hard reset detected"),
            ("clean -fd", "Force clean detected"),
            ("branch -D", "Force branch delete detected"),
        ]

        for pattern, message in dangerous_patterns:
            if pattern in tool_input:
                # Check if it's to main/master
                if any(branch in tool_input for branch in ["main", "master"]):
                    print(f"🚫 BLOCKED: {message} on main/master branch", file=sys.stderr)
                    sys.exit(1)  # Block dangerous operation

                # Warn for other branches
                print(f"⚠️ WARNING: {message}", file=sys.stderr)
                return {"status": "warning", "operation": pattern}

        return {"status": "success", "git_operation": "safe"}
