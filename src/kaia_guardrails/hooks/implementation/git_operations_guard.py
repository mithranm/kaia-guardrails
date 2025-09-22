"""
Git Operations Guard Hook

Prevents direct git commit, reset, merge, and branch operations outside of the focus process manager.
Enforces that all git operations go through the controlled focus process workflow.
"""
import os
import re
from typing import Dict, Any

from kaia_guardrails.hooks.base import HookBase, HookError


class GitOperationsGuardHook(HookBase):
    """Hook that blocks direct git operations and enforces focus process manager usage."""

    def __init__(self):
        super().__init__(name="git_operations_guard", priority=5)  # Run early to block operations

    def run(self, context: Dict[str, Any]) -> Any:
        """Block dangerous git operations that bypass focus process manager."""
        # Only run on PreToolUse to block before operations
        if context.get('hook_type') != 'PreToolUse':
            return None

        tool_name = context.get('tool_name', '')
        tool_input = context.get('tool_input', {})

        # Only check Bash commands
        if tool_name != 'Bash':
            return None

        command = tool_input.get('command', '')
        if not command:
            return None

        # Check for dangerous git operations
        dangerous_operation = self._analyze_git_command(command)
        if dangerous_operation:
            return self._handle_dangerous_operation(dangerous_operation, command)

        return None

    def _analyze_git_command(self, command: str) -> Dict[str, Any]:
        """
        Analyze a bash command to detect dangerous git operations.

        Returns:
            Dict with operation info if dangerous, None if safe
        """
        # Normalize command (remove extra whitespace, handle line continuations)
        normalized_cmd = ' '.join(command.split())

        # Patterns for dangerous git operations
        dangerous_patterns = [
            {
                'pattern': r'\bgit\s+commit\b',
                'operation': 'commit',
                'reason': 'Direct git commits bypass focus process auto-commit system',
                'suggestion': 'Use focus process manager auto-commit or complete the current focus'
            },
            {
                'pattern': r'\bgit\s+reset\b',
                'operation': 'reset',
                'reason': 'Direct git reset can corrupt focus process state tracking',
                'suggestion': 'Use focus process manager escape hatch for controlled rollbacks'
            },
            {
                'pattern': r'\bgit\s+merge\b',
                'operation': 'merge',
                'reason': 'Direct merges bypass focus process completion workflow',
                'suggestion': 'Use focus process manager complete_current_focus() for proper merging'
            },
            {
                'pattern': r'\bgit\s+rebase\b',
                'operation': 'rebase',
                'reason': 'Direct rebasing can disrupt focus process commit metadata',
                'suggestion': 'Use focus process manager semantic escape targeting instead'
            },
            {
                'pattern': r'\bgit\s+checkout\s+[^-]',
                'operation': 'branch_switch',
                'reason': 'Direct branch switching bypasses focus process state management',
                'suggestion': 'Use focus process manager to switch between focuses'
            },
            {
                'pattern': r'\bgit\s+branch\s+(-d|-D|--delete)',
                'operation': 'branch_delete',
                'reason': 'Direct branch deletion can orphan focus process tracking',
                'suggestion': 'Let focus process manager handle branch cleanup after completion'
            },
            {
                'pattern': r'\bgit\s+stash\s+(pop|apply)',
                'operation': 'stash_apply',
                'reason': 'Direct stash operations can conflict with focus process commits',
                'suggestion': 'Complete current focus before applying stashed changes'
            }
        ]

        # Check for each dangerous pattern
        for pattern_info in dangerous_patterns:
            if re.search(pattern_info['pattern'], normalized_cmd, re.IGNORECASE):
                return {
                    'operation': pattern_info['operation'],
                    'reason': pattern_info['reason'],
                    'suggestion': pattern_info['suggestion'],
                    'command': command
                }

        # Special case: Allow safe git operations
        safe_patterns = [
            r'\bgit\s+status\b',
            r'\bgit\s+log\b',
            r'\bgit\s+show\b',
            r'\bgit\s+diff\b',
            r'\bgit\s+branch\s*$',  # List branches only
            r'\bgit\s+remote\b',
            r'\bgit\s+config\b',
            r'\bgit\s+ls-files\b',
            r'\bgit\s+rev-parse\b',
            r'\bgit\s+rev-list\b'
        ]

        # If it's a git command but not in safe patterns, it might be dangerous
        if re.search(r'\bgit\s+', normalized_cmd, re.IGNORECASE):
            for safe_pattern in safe_patterns:
                if re.search(safe_pattern, normalized_cmd, re.IGNORECASE):
                    return None  # Safe git operation

            # Unknown git operation - be cautious
            return {
                'operation': 'unknown_git',
                'reason': 'Unknown git operation detected - might interfere with focus process management',
                'suggestion': 'Use known safe git operations (status, log, diff) or focus process manager methods',
                'command': command
            }

        return None  # Not a git command or safe operation

    def _handle_dangerous_operation(self, operation_info: Dict[str, Any], command: str) -> Any:
        """Handle detection of a dangerous git operation."""
        # Check for override flags first
        if self._check_for_override():
            # Track override usage and get any reset messages
            from .override_usage_tracker import get_override_tracker
            tracker = get_override_tracker()
            tracker_message = tracker.track_override_usage("git_operations", "git_operations_guard")

            print(f"[GIT-GUARD] Override flag detected - allowing dangerous git operation: {operation_info['operation']}")

            if tracker_message:
                print(f"[GIT-GUARD] {tracker_message}")

            return None  # Allow operation to proceed

        operation = operation_info['operation']
        reason = operation_info['reason']
        suggestion = operation_info['suggestion']

        # Get current focus context for better error messages
        focus_context = self._get_focus_context()

        if focus_context.get('active_focus'):
            focus_info = f"\\nCurrent focus: {focus_context['active_focus']} (depth: {focus_context['stack_depth']})"
        else:
            focus_info = "\\nNo active focus process"

        error_msg = f"""BLOCKED: Dangerous git operation '{operation}' detected

Command: {command}

Reason: {reason}

{focus_info}

Recommendation: {suggestion}

Available focus process manager methods:
  - manager.complete_current_focus()     # Complete and merge current focus
  - manager.escape_to_semantic_target()  # Intelligent escape from problems
  - manager.trigger_escape_hatch()       # Manual escape with level control
  - manager.force_remote_push()          # Push to remote when needed

For safe git operations, use: git status, git log, git diff, git show

EMERGENCY OVERRIDE: If you absolutely must bypass this guardrail, set:
  export KAIA_GUARDRAILS_OVERRIDE=git_operations
  # Then run your command
  unset KAIA_GUARDRAILS_OVERRIDE

WARNING: Using the override may corrupt focus process state tracking!"""

        raise HookError(error_msg)

    def _check_for_override(self) -> bool:
        """
        Check for environment variable override.

        Returns:
            True if override is active for git operations
        """
        override_value = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()

        # Check for specific git operations override
        if override_value in ['git_operations', 'git', 'all', 'true']:
            return True

        # Check for global emergency override
        emergency_override = os.environ.get('KAIA_EMERGENCY_OVERRIDE', '').lower()
        if emergency_override in ['true', '1', 'yes']:
            return True

        return False

    def _get_focus_context(self) -> Dict[str, Any]:
        """Get current focus process context for error messages."""
        try:
            from .focus_process_manager import FocusProcessManager
            manager = FocusProcessManager()
            focus_info = manager.get_current_focus_info()

            return {
                'active_focus': focus_info.get('focus_id'),
                'stack_depth': focus_info.get('stack_depth', 0),
                'branch_name': focus_info.get('branch_name'),
                'auto_commit': focus_info.get('auto_commit', False)
            }
        except Exception:
            return {'active_focus': None, 'stack_depth': 0}

    def _is_emergency_override(self, command: str) -> bool:
        """
        Check if command contains emergency override flag.

        Emergency overrides should be rare and well-documented.
        """
        # Look for special override flag in command
        override_patterns = [
            r'--focus-manager-override',
            r'# EMERGENCY: focus manager bypass',
            r'FOCUS_EMERGENCY_OVERRIDE=true'
        ]

        for pattern in override_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                print(f"[GIT-GUARD] Emergency override detected in command: {command}")
                return True

        return False