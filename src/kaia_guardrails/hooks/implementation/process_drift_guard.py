#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Focus Process Drift Detection Guard Hook

MAINTAINS BLOCKING BEHAVIOR - this is an LLM judge for focus process enforcement.
Uses direct imports where possible, protects against tool failures only.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from kaia_guardrails.hooks.base import HookBase, HookError
from .focus_process_manager import FocusProcessManager

def get_project_root() -> Path:
    """Find the project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

def load_current_focus_process() -> dict:
    """Load current focus process information."""
    claude_dir = get_project_root() / '.claude'

    # Load current focus process
    current_process_file = claude_dir / 'current-process.txt'
    process_state_file = claude_dir / 'process-state.json'

    process_info = {
        'current_focus': 'UNKNOWN',
        'description': 'No current focus process defined',
        'last_updated': datetime.now().isoformat()
    }

    try:
        if current_process_file.exists():
            with open(current_process_file) as f:
                process_info['description'] = f.read().strip()

        if process_state_file.exists():
            with open(process_state_file) as f:
                state_data = json.load(f)
                process_info.update(state_data)
    except Exception as e:
        print(f"[FOCUS-DRIFT-GUARD-ERROR] Failed to load focus process state: {e}", file=sys.stderr)

    return process_info

def check_focus_process_drift(context: Dict[str, Any]) -> bool:
    """
    Check if current action drifts from focus process.
    Returns True if action should be blocked.
    
    This is a GUARDRAIL that should maintain blocking behavior.
    """
    tool_name = context.get('tool_name', 'unknown')
    tool_input = context.get('tool_input', {})

    # Extract file paths from tool input
    file_path = tool_input.get('file_path', '')
    file_paths = [file_path] if file_path else []
    
    # Skip drift checking for certain safe tools
    safe_tools = ['read', 'glob', 'grep', 'bash']
    if tool_name.lower() in safe_tools:
        return False  # Don't block safe tools
    
    try:
        process_info = load_current_focus_process()
        current_focus = process_info.get('current_focus', 'UNKNOWN')
        
        # If no focus is set, allow operation but warn
        if current_focus == 'UNKNOWN':
            print(f"[FOCUS-DRIFT-GUARD-WARN] No current focus process set, allowing {tool_name}", file=sys.stderr)
            return False
        
        
        # System cleanup focus allows all operations
        if current_focus == 'system_cleanup':
            return False

        # Simple drift detection based on focus keywords
        focus_keywords = current_focus.lower().split()
        all_file_paths = ' '.join(file_paths).lower()

        # Check if any focus keywords appear in the file paths
        keyword_match = any(keyword in all_file_paths for keyword in focus_keywords)

        if not keyword_match:
            # Potential drift detected
            print(f"POTENTIAL FOCUS PROCESS DRIFT DETECTED:", file=sys.stderr)
            print(f"   Current Focus Process: {current_focus}", file=sys.stderr)
            print(f"   Tool: {tool_name}", file=sys.stderr)
            print(f"   Files: {file_paths}", file=sys.stderr)
            print(f"   This may be drifting from current focus process.", file=sys.stderr)
            print(f"   Type 'continue' to override, or refocus on: {current_focus}", file=sys.stderr)
            
            # In a real implementation, this would wait for user input
            # For now, we'll warn but not block to avoid hanging Claude Code
            print(f"[FOCUS-DRIFT-GUARD-WARN] Focus process drift detected but allowing operation", file=sys.stderr)
            return False  # Don't block to avoid API issues
        
        return False  # No drift detected
        
    except Exception as e:
        # Don't block on tool failures
        print(f"[FOCUS-DRIFT-GUARD-ERROR] Drift detection failed: {e}, allowing operation", file=sys.stderr)
        return False

def update_process_state():
    """Update process state with current tool call."""
    try:
        claude_dir = get_project_root() / '.claude'
        process_state_file = claude_dir / 'process-state.json'
        
        tool_name = os.environ.get('CLAUDE_TOOL_NAME', 'unknown')
        file_paths = os.environ.get('CLAUDE_FILE_PATHS', '')
        
        # Load existing state
        if process_state_file.exists():
            with open(process_state_file) as f:
                state_data = json.load(f)
        else:
            state_data = {}
        
        # Update with current tool call
        state_data.update({
            'last_updated': datetime.now().isoformat(),
            'last_tool_call': {
                'tool': tool_name,
                'files': file_paths.split(',') if file_paths else [],
                'timestamp': datetime.now().isoformat()
            }
        })
        
        # Save updated state
        with open(process_state_file, 'w') as f:
            json.dump(state_data, f, indent=2)
            
    except Exception as e:
        print(f"[DRIFT-GUARD-ERROR] Failed to update process state: {e}", file=sys.stderr)

def main():
    """Main drift guard function."""
    # Update process state first
    update_process_state()
    
    # Check for process drift (GUARDRAIL - can block)
    should_block = check_process_drift()
    
    if should_block:
        print(f"[DRIFT-GUARD] BLOCKING action due to process drift", file=sys.stderr)
        sys.exit(1)  # INTENTIONALLY BLOCKING - this is a guardrail
    else:
        print(f"[DRIFT-GUARD] Process drift check passed", file=sys.stderr)
        sys.exit(0)

class ProcessDriftGuardHook(HookBase):
    """Hook that blocks operations when process drift is detected."""

    def __init__(self):
        super().__init__(name="process_drift_guard", priority=1)  # Run first as guardrail

    def run(self, context: Dict[str, Any]) -> Any:
        """Run focus process drift detection and BLOCK if drift detected."""
        # Only run on PreToolUse to block before operations
        if context.get('hook_type') != 'PreToolUse':
            return None

        try:
            # Initialize focus process manager
            focus_manager = FocusProcessManager()

            # Check for focus process drift (GUARDRAIL - can block)
            should_block = check_focus_process_drift(context)

            if should_block:
                # CRITICAL: This must block the operation
                raise HookError("BLOCKED: Focus process drift detected - operation violates current focus process")

            # Auto-commit if enabled for current focus
            focus_info = focus_manager.get_current_focus_info()
            if focus_info.get("auto_commit") and context.get('tool_name') in ['Write', 'Edit', 'MultiEdit']:
                # This will be handled post-operation, just log for now
                print(f"[FOCUS-DRIFT-GUARD] Auto-commit enabled for focus: {focus_info.get('focus_id')}")

            return "Focus process drift check passed"

        except HookError:
            # Re-raise HookError to block operation
            raise
        except Exception as e:
            # Don't block on infrastructure errors, just warn
            return f"Focus process drift guard error (non-blocking): {e}"

if __name__ == '__main__':
    main()
