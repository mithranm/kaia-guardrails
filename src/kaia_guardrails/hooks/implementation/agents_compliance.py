"""AGENTS.md compliance checker."""

import os
import sys
from pathlib import Path

from ...utils import find_agents_files, read_all_agents_content
from ..base import HookBase


class AgentsComplianceHook(HookBase):
    """Checks compliance with AGENTS.*.md guidelines."""

    def __init__(self):
        super().__init__(name="agents_compliance", priority=40)

    def run(self, context: dict) -> dict:
        """Check compliance with AGENTS.*.md files."""
        project_root = Path(context.get("project_root", Path.cwd()))
        agents_files = find_agents_files(project_root)

        if not agents_files:
            return {"status": "skipped", "reason": "no AGENTS.*.md files"}

        # Basic checks
        violations = []

        # Read all AGENTS.*.md content
        agents_content = read_all_agents_content(project_root)

        # Look for environment requirement in AGENTS.md
        if "conda" in agents_content.lower() or "environment" in agents_content.lower():
            # Check if we're in any conda env
            python_path = sys.executable
            if "conda" not in python_path and "envs" not in python_path:
                violations.append("Not using a conda environment (required by AGENTS.md)")

        # Check working directory
        cwd = Path.cwd()
        if not str(cwd).startswith(str(project_root)):
            violations.append(f"Working outside project directory: {cwd}")

        # Check for emoji usage (common AGENTS.*.md rule)
        tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
        if any(ord(c) > 127 for c in tool_input):  # Basic emoji detection
            # Check if any AGENTS file prohibits emoji
            if "no emoji" in agents_content.lower():
                violations.append("Emoji usage detected (prohibited by AGENTS.*.md)")

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
