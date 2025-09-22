"""
Emoji validation hook for Claude Code.
Blocks file edits that contain emojis.
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from kaia_guardrails.hooks.base import HookBase, HookError

# Comprehensive emoji pattern
EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"  # Emoticons
    r"\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    r"\U0001F680-\U0001F6FF"  # Transport and Map Symbols
    r"\U0001F1E0-\U0001F1FF"  # Regional Indicator Symbols
    r"\U0001F700-\U0001F77F"  # Alchemical Symbols
    r"\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    r"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    r"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    r"\U0001FA00-\U0001FA6F"  # Chess Symbols
    r"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    r"\U00002600-\U000026FF"  # Miscellaneous Symbols
    r"\U00002700-\U000027BF"  # Dingbats
    r"\U0000FE00-\U0000FE0F"  # Variation Selectors
    r"]+"
)

def check_file_for_emojis(file_path: str) -> tuple[bool, list[str]]:
    """Check if file contains emojis. Returns (has_emojis, error_messages)."""
    try:
        path = Path(file_path)
        if not path.exists():
            return False, []

        content = path.read_text(encoding='utf-8')
        lines = content.splitlines()
        errors = []

        for line_num, line in enumerate(lines, 1):
            matches = EMOJI_PATTERN.findall(line)
            if matches:
                emojis = "".join(matches)
                errors.append(f"Line {line_num}: Found emoji(s): {emojis}")

        return len(errors) > 0, errors

    def _check_for_override(self) -> bool:
        """
        Check for environment variable override.

        Returns:
            True if override is active for emoji checking
        """
        override_value = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()

        # Check for specific emoji check override
        if override_value in ['emoji_check', 'emoji', 'all', 'true']:
            return True

        # Check for global emergency override
        emergency_override = os.environ.get('KAIA_EMERGENCY_OVERRIDE', '').lower()
        if emergency_override in ['true', '1', 'yes']:
            return True

        return False
    except Exception as e:
        return False, [f"Error reading file: {e}"]

class EmojiCheckHook(HookBase):
    """Hook that validates files for emoji content before edits."""

    def __init__(self):
        super().__init__(name="emoji_check", priority=10)

    def _record_quality_violation(self, gate_type: str, message: str):
        """Record a quality gate violation for focus process exit evaluation."""
        try:
            import json
            from pathlib import Path

            # Store in claude directory for focus process manager
            project_root = Path.cwd()
            claude_dir = project_root / '.claude'
            violations_file = claude_dir / 'quality_violations.json'

            # Load existing violations
            violations = {}
            if violations_file.exists():
                violations = json.loads(violations_file.read_text())

            # Add this violation
            if gate_type not in violations:
                violations[gate_type] = []

            violation = {
                'timestamp': str(datetime.now()),
                'message': message,
                'tool_operation': True  # Mark as from actual operation
            }

            violations[gate_type].append(violation)

            # Save violations
            claude_dir.mkdir(exist_ok=True)
            violations_file.write_text(json.dumps(violations, indent=2))

        except Exception:
            pass  # Don't fail hook if recording fails

    def run(self, context: Dict[str, Any]) -> Any:
        """Check for emojis using full Claude Code context."""
        hook_type = context.get('hook_type')
        tool_name = context.get('tool_name', '')
        tool_input = context.get('tool_input', {})

        # Only check file editing operations
        if tool_name not in ['Write', 'Edit', 'MultiEdit']:
            return None

        has_emojis = False
        emoji_errors = []

        if hook_type == 'PreToolUse':
            # Check content that will be written/edited
            if tool_name == 'Write':
                content = tool_input.get('content', '')
                if content:
                    has_emojis, emoji_errors = self._check_content_for_emojis(content)

            elif tool_name == 'Edit':
                new_content = tool_input.get('new_string', '')
                if new_content:
                    has_emojis, emoji_errors = self._check_content_for_emojis(new_content)

            elif tool_name == 'MultiEdit':
                edits = tool_input.get('edits', [])
                for edit in edits:
                    new_content = edit.get('new_string', '')
                    if new_content:
                        edit_has_emojis, edit_errors = self._check_content_for_emojis(new_content)
                        if edit_has_emojis:
                            has_emojis = True
                            emoji_errors.extend(edit_errors)

            # BLOCK if emojis found in PreToolUse (unless override is set)
            if has_emojis:
                if self._check_for_override():
                    # Track override usage and get any reset messages
                    from .override_usage_tracker import get_override_tracker
                    tracker = get_override_tracker()
                    tracker_message = tracker.track_override_usage("emoji_check", "emoji_check")

                    print(f"[EMOJI-CHECK] Override flag detected - allowing emoji content in {tool_name}")
                    base_message = f"Override: Allowing emoji content (override active)"

                    if tracker_message:
                        return f"{base_message}\n\n{tracker_message}"
                    else:
                        return base_message

                error_msg = f"BLOCKED: Emojis found in {tool_name} operation\n"
                for error in emoji_errors:
                    error_msg += f"  {error}\n"
                error_msg += "  Remove emojis before editing to avoid encoding issues.\n\n"
                error_msg += "EMERGENCY OVERRIDE: If you absolutely must use emojis, set:\n"
                error_msg += "  export KAIA_GUARDRAILS_OVERRIDE=emoji_check\n"
                error_msg += "  # Then run your command\n"
                error_msg += "  unset KAIA_GUARDRAILS_OVERRIDE\n\n"
                error_msg += "WARNING: Emojis may cause encoding issues in some environments!"

                # Store quality gate violation for focus process exit
                self._record_quality_violation("emoji_check", error_msg)

                # Only warn, don't block normal operations
                return f"⚠️ QUALITY GATE: {error_msg}"

        elif hook_type == 'PostToolUse':
            # Check the actual file after operation
            file_path = tool_input.get('file_path', '')
            if file_path:
                has_emojis, emoji_errors = check_file_for_emojis(file_path)
                if has_emojis:
                    warning_msg = f"WARNING: Emojis found in {file_path}\n"
                    for error in emoji_errors:
                        warning_msg += f"  {error}\n"
                    warning_msg += "  Consider removing emojis to avoid encoding issues."
                    return warning_msg

        return None

    def _check_content_for_emojis(self, content: str) -> tuple[bool, list[str]]:
        """Check if content contains emojis. Returns (has_emojis, error_messages)."""
        lines = content.splitlines()
        errors = []

        for line_num, line in enumerate(lines, 1):
            matches = EMOJI_PATTERN.findall(line)
            if matches:
                emojis = "".join(matches)
                errors.append(f"Line {line_num}: Found emoji(s): {emojis}")

        return len(errors) > 0, errors

    def _check_for_override(self) -> bool:
        """
        Check for environment variable override.

        Returns:
            True if override is active for emoji checking
        """
        override_value = os.environ.get('KAIA_GUARDRAILS_OVERRIDE', '').lower()

        # Check for specific emoji check override
        if override_value in ['emoji_check', 'emoji', 'all', 'true']:
            return True

        # Check for global emergency override
        emergency_override = os.environ.get('KAIA_EMERGENCY_OVERRIDE', '').lower()
        if emergency_override in ['true', '1', 'yes']:
            return True

        return False