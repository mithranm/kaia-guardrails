"""AGENTS.md compliance checker."""

import os
import sys
from pathlib import Path

from ..base import HookBase


class AgentsComplianceHook(HookBase):
    """Checks compliance with AGENTS.md guidelines."""

    def __init__(self):
        super().__init__(name="agents_compliance", priority=40)

    def run(self, context: dict) -> dict:
        """Check compliance with AGENTS.md."""
        project_root = Path(context.get("project_root", Path.cwd()))
        agents_file = project_root / "AGENTS.instructions.md"

        if not agents_file.exists():
            return {"status": "skipped", "reason": "no AGENTS.instructions.md"}

        # Basic checks
        violations = []

        # Check conda environment
        python_path = sys.executable
        if "mcp-unified" not in python_path:
            violations.append("Not using mcp-unified conda environment")

        # Check working directory
        cwd = Path.cwd()
        if not str(cwd).startswith(str(project_root)):
            violations.append(f"Working outside project directory: {cwd}")

        # Check for emoji usage (common AGENTS.md rule)
        tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
        if any(ord(c) > 127 for c in tool_input):  # Basic emoji detection
            # Check if AGENTS.md prohibits emoji
            with open(agents_file) as f:
                if "no emoji" in f.read().lower():
                    violations.append("Emoji usage detected (prohibited by AGENTS.md)")

        if violations:
            print("⚠️ AGENTS.md compliance issues:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)

            # Only block on critical violations (wrong directory)
            if any("outside project" in v for v in violations):
                print("🚫 BLOCKED: Working outside project directory", file=sys.stderr)
                sys.exit(1)

            return {"status": "warning", "violations": violations}

        return {"status": "success", "compliant": True}
