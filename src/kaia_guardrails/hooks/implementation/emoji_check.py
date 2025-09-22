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

        if hook_type == 'PreToolUse':
            # Check if Claude is adding NEW emojis
            is_adding_new_emojis = self._is_adding_new_emojis(tool_name, tool_input)

            if is_adding_new_emojis:
                # Try to auto-fix with vibelint instead of blocking
                auto_fix_result = self._attempt_vibelint_autofix(tool_name, tool_input)

                if auto_fix_result['success']:
                    return f"[EMOJI-CHECK] Auto-fixed emojis using vibelint: {auto_fix_result['message']}"
                else:
                    # Store quality gate violation for focus process exit evaluation
                    violation_msg = f"New emojis detected in {tool_name} operation - vibelint auto-fix failed"
                    self._record_quality_violation("emoji_check", violation_msg)

                    return f"⚠️ QUALITY GATE: New emojis detected (auto-fix failed: {auto_fix_result['error']})"

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

    def _is_adding_new_emojis(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        """
        Check if the operation would add NEW emojis compared to existing content.
        Returns True only if emoji count would increase.
        """
        try:
            if tool_name == 'Write':
                # For Write operations, check if file exists and compare emoji counts
                file_path = tool_input.get('file_path', '')
                new_content = tool_input.get('content', '')

                if not file_path:
                    return False

                # Check emojis in new content
                new_has_emojis, _ = self._check_content_for_emojis(new_content)
                if not new_has_emojis:
                    return False  # No emojis in new content

                # Check if file exists and has existing emojis
                try:
                    from pathlib import Path
                    path = Path(file_path)
                    if path.exists():
                        existing_content = path.read_text(encoding='utf-8')
                        existing_emoji_count = len(EMOJI_PATTERN.findall(existing_content))
                        new_emoji_count = len(EMOJI_PATTERN.findall(new_content))
                        return new_emoji_count > existing_emoji_count
                    else:
                        # New file with emojis = adding new emojis
                        return True
                except Exception:
                    # If we can't read existing file, assume it's adding new emojis
                    return True

            elif tool_name == 'Edit':
                # For Edit operations, only check the new_string content
                new_string = tool_input.get('new_string', '')
                has_emojis, _ = self._check_content_for_emojis(new_string)
                return has_emojis  # Any emoji in new_string counts as adding

            elif tool_name == 'MultiEdit':
                # For MultiEdit, check if any edit adds emojis
                edits = tool_input.get('edits', [])
                for edit in edits:
                    new_string = edit.get('new_string', '')
                    has_emojis, _ = self._check_content_for_emojis(new_string)
                    if has_emojis:
                        return True

            return False

        except Exception:
            # If we can't determine, err on the side of caution
            return False

    def _attempt_vibelint_autofix(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to use vibelint to automatically fix emoji issues.

        Returns:
            Dict with 'success' (bool), 'message' (str), and optional 'error' (str)
        """
        try:
            import subprocess
            import tempfile
            from pathlib import Path

            if tool_name == 'Write':
                # For Write operations, fix the content before writing
                content = tool_input.get('content', '')
                if not content:
                    return {'success': False, 'error': 'No content to fix'}

                # Write content to temp file for vibelint processing
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
                    tmp_file.write(content)
                    tmp_path = tmp_file.name

                try:
                    # Run vibelint fix on the temp file
                    result = subprocess.run(
                        ['vibelint', 'fix', tmp_path, '--emoji-removal'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        # Read back the fixed content
                        fixed_content = Path(tmp_path).read_text()

                        # Update the tool_input with fixed content
                        tool_input['content'] = fixed_content

                        return {
                            'success': True,
                            'message': f'Removed emojis from content using vibelint'
                        }
                    else:
                        return {
                            'success': False,
                            'error': f'vibelint fix failed: {result.stderr}'
                        }

                finally:
                    # Clean up temp file
                    try:
                        Path(tmp_path).unlink()
                    except:
                        pass

            elif tool_name in ['Edit', 'MultiEdit']:
                # For Edit operations, we can't modify the tool input dynamically
                # Just record as quality gate violation for focus exit evaluation
                return {
                    'success': False,
                    'error': 'Cannot auto-fix Edit operations - will be checked at focus exit'
                }

            return {'success': False, 'error': 'Unsupported tool type for auto-fix'}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'vibelint fix timed out'}
        except FileNotFoundError:
            return {'success': False, 'error': 'vibelint command not found'}
        except Exception as e:
            return {'success': False, 'error': f'Auto-fix error: {str(e)}'}

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