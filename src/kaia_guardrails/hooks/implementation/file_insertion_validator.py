"""
File Insertion Validator Hook

Validates file placement using vibelint LLM before files are created.
Ensures files are placed in appropriate locations within the project structure.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any

from kaia_guardrails.hooks.base import HookBase, HookError


class FileInsertionValidatorHook(HookBase):
    """Hook that validates file placement before creation using vibelint LLM."""

    def __init__(self):
        super().__init__(name="file_insertion_validator", priority=3)  # Run early

    def run(self, context: Dict[str, Any]) -> Any:
        """Validate file placement before creation."""
        # Only run on PreToolUse for file creation operations
        if context.get('hook_type') != 'PreToolUse':
            return None

        tool_name = context.get('tool_name', '')
        tool_input = context.get('tool_input', {})

        # Only check Write operations (new file creation)
        if tool_name != 'Write':
            return None

        file_path = tool_input.get('file_path', '')
        if not file_path:
            return None

        # Skip validation for files in .claude directory (system files)
        if '.claude' in file_path:
            return None

        # Check if file already exists (Edit operations should use Edit tool)
        if os.path.exists(file_path):
            return None

        # Validate file placement
        is_valid, reason = self._validate_file_placement(file_path, tool_input.get('content', ''))

        if not is_valid:
            error_msg = f"""BLOCKED: File placement validation failed

File: {file_path}
Reason: {reason}

The vibelint LLM determined this file placement is inappropriate for the project structure.

EMERGENCY OVERRIDE: If you absolutely must bypass this validation:

Option 1 (Normal shell):
  export KAIA_GUARDRAILS_OVERRIDE=file_placement
  # Then run your command
  unset KAIA_GUARDRAILS_OVERRIDE

Option 2 (Claude Code compatible):
  echo "file_placement" > .claude/file_placement_override_active
  # Then run your Write operation
  rm .claude/file_placement_override_active

WARNING: Bypassing file placement validation may result in poor project organization!"""

            raise HookError(error_msg)

        return None

    def _validate_file_placement(self, file_path: str, content: str) -> tuple[bool, str]:
        """
        Validate file placement using vibelint LLM.

        Args:
            file_path: Path where the file will be created
            content: Content of the file being created

        Returns:
            (is_valid, reason) tuple
        """
        # Check for override first
        if self._check_for_override():
            return True, "Override active"

        # Use LLM judge utility for file placement validation - NO FALLBACKS
        from kaia_guardrails.llm_judge import validate_file_placement

        # Analyze project structure
        project_root = Path.cwd()
        relative_path = Path(file_path).relative_to(project_root)

        # Build context about existing project structure
        structure_context = self._get_project_structure_context(project_root)

        # Use LLM judge - FAIL HARD IF IT DOESN'T WORK
        try:
            is_appropriate = validate_file_placement(
                file_path=str(relative_path),
                content=content,
                project_structure=structure_context
            )

            if is_appropriate:
                return True, "File placement approved by LLM"
            else:
                return False, "File placement rejected by LLM"

        except Exception as e:
            # Re-raise - no fallbacks, fail hard
            raise Exception(f"LLM file placement validation failed: {e}") from e

    def _get_project_structure_context(self, project_root: Path) -> str:
        """Build context about the project structure."""
        structure = []

        # Get top-level directories
        for item in sorted(project_root.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                structure.append(f"📁 {item.name}/")

                # Sample a few files from each directory
                files = list(item.glob('*'))[:5]
                for file in files:
                    if file.is_file():
                        structure.append(f"   📄 {file.name}")

                if len(files) > 5:
                    structure.append(f"   ... ({len(list(item.glob('*'))) - 5} more files)")

        return '\n'.join(structure[:50])  # Limit output

    def _check_for_override(self) -> bool:
        """Check for file placement override."""
        # Check environment variable
        override_value = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()
        if override_value in ['file_placement', 'all', 'true']:
            return True

        # Check file-based override
        try:
            override_file = Path.cwd() / '.claude' / 'file_placement_override_active'
            if override_file.exists():
                file_override = override_file.read_text().strip().lower()
                if file_override in ['file_placement', 'all', 'true']:
                    return True
        except Exception:
            pass

        return False