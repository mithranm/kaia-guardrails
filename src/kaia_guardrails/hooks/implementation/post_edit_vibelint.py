"""Post-edit vibelint validation hook."""

import os
import subprocess
import sys
from pathlib import Path

from ..base import HookBase


class PostEditVibelintHook(HookBase):
    """Runs vibelint after edit operations, blocks on critical issues."""

    def __init__(self):
        super().__init__(name="post_edit_vibelint", priority=50)

    def run(self, context: dict) -> dict:
        """Run vibelint validation after edit operations."""
        tool_name = os.environ.get("CLAUDE_TOOL_NAME", "").lower()

        # Only run after edit operations
        if tool_name not in ["edit", "write", "notebookedit"]:
            return {"status": "skipped", "reason": "not an edit operation"}

        # Get edited files
        file_paths = os.environ.get("CLAUDE_FILE_PATHS", "").split(",")
        file_paths = [f.strip() for f in file_paths if f.strip()]

        if not file_paths:
            return {"status": "skipped", "reason": "no files edited"}

        # Filter for Python files only
        py_files = [f for f in file_paths if f.endswith(".py")]
        if not py_files:
            return {"status": "skipped", "reason": "no Python files edited"}

        # Run vibelint on edited files
        try:
            result = subprocess.run(
                ["vibelint", "check", "--output=json"] + py_files,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse output
            if result.returncode == 0:
                return {"status": "success", "issues": []}

            # Check for critical issues (BLOCK severity)
            output = result.stdout or result.stderr
            if "BLOCK" in output or "SECURITY" in output.upper():
                print(f"🚫 CRITICAL vibelint issues found in {', '.join(py_files)}", file=sys.stderr)
                print(output, file=sys.stderr)
                sys.exit(1)  # Block the operation

            # Non-critical issues - warn but allow
            print(f"⚠️ Vibelint found issues in {', '.join(py_files)}", file=sys.stderr)
            print(output, file=sys.stderr)
            return {"status": "warning", "issues": output}

        except subprocess.TimeoutExpired:
            print("⚠️ Vibelint check timed out", file=sys.stderr)
            return {"status": "timeout"}
        except FileNotFoundError:
            print("⚠️ Vibelint not installed - skipping validation", file=sys.stderr)
            return {"status": "skipped", "reason": "vibelint not installed"}
        except Exception as e:
            print(f"⚠️ Vibelint check failed: {e}", file=sys.stderr)
            return {"status": "error", "error": str(e)}
