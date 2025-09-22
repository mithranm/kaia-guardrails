"""
Focus Process Auto-Commit Hook

Automatically commits every tool call when in a focus process.
Each tool call becomes a git commit for precise rollback capability.
"""
from typing import Dict, Any
from pathlib import Path

from kaia_guardrails.hooks.base import HookBase
from .focus_process_manager import FocusProcessManager


class FocusAutoCommitHook(HookBase):
    """Hook that auto-commits tool calls when in focus process mode."""

    def __init__(self):
        super().__init__(name="focus_auto_commit", priority=100)  # Run after other hooks

    def run(self, context: Dict[str, Any]) -> Any:
        """Auto-commit tool calls when in focus process with auto-commit enabled."""
        hook_type = context.get('hook_type')

        # Only run on PostToolUse to commit after successful operations
        if hook_type != 'PostToolUse':
            return None

        try:
            # Initialize focus process manager
            focus_manager = FocusProcessManager()
            focus_info = focus_manager.get_current_focus_info()

            # Only auto-commit if we're in a focus process with auto-commit enabled
            if not focus_info.get('focus_id') or not focus_info.get('auto_commit'):
                return None

            tool_name = context.get('tool_name', 'unknown')
            tool_input = context.get('tool_input', {})

            # Extract file paths from tool input
            file_paths = []

            # Handle different tool types
            if tool_name in ['Write', 'Edit']:
                file_path = tool_input.get('file_path')
                if file_path:
                    file_paths.append(file_path)

            elif tool_name == 'MultiEdit':
                file_path = tool_input.get('file_path')
                if file_path:
                    file_paths.append(file_path)

            elif tool_name == 'NotebookEdit':
                notebook_path = tool_input.get('notebook_path')
                if notebook_path:
                    file_paths.append(notebook_path)

            # Auto-commit if we have file paths to commit
            if file_paths:
                description = self._generate_commit_description(tool_name, tool_input)
                success = focus_manager.auto_commit_tool_call(
                    tool_name,
                    file_paths,
                    description,
                    tool_input  # Pass tool input for rich metadata
                )

                if success:
                    return f"Auto-committed {tool_name} for focus: {focus_info['focus_id']}"
                else:
                    return f"Auto-commit failed for {tool_name}"

            return None

        except Exception as e:
            # Don't block operations if auto-commit fails
            return f"Focus auto-commit error (non-blocking): {e}"

    def _generate_commit_description(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Generate a descriptive commit message based on the tool and input."""
        if tool_name == 'Write':
            file_path = tool_input.get('file_path', 'unknown')
            content_preview = tool_input.get('content', '')[:100]
            if len(content_preview) == 100:
                content_preview += "..."
            return f"Create/update {Path(file_path).name}: {content_preview}"

        elif tool_name == 'Edit':
            file_path = tool_input.get('file_path', 'unknown')
            old_string = tool_input.get('old_string', '')[:50]
            new_string = tool_input.get('new_string', '')[:50]
            if len(old_string) == 50:
                old_string += "..."
            if len(new_string) == 50:
                new_string += "..."
            return f"Edit {Path(file_path).name}: '{old_string}' -> '{new_string}'"

        elif tool_name == 'MultiEdit':
            file_path = tool_input.get('file_path', 'unknown')
            edits = tool_input.get('edits', [])
            edit_count = len(edits)
            return f"MultiEdit {Path(file_path).name}: {edit_count} change(s)"

        elif tool_name == 'NotebookEdit':
            notebook_path = tool_input.get('notebook_path', 'unknown')
            return f"Edit notebook {Path(notebook_path).name}"

        else:
            return f"{tool_name} operation"