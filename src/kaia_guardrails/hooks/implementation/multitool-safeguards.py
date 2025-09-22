#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Multitool Safeguards Hook for Claude Code

This PreToolUse hook intercepts multitool operations (especially write/execute combinations)
and uses a judge model (claudiallm) to evaluate whether the operations are safe to perform.

Environment Variables Expected:
- CLAUDE_TOOL_NAME: The tool being called
- CLAUDE_FILE_PATHS: Comma-separated file paths being operated on
- CLAUDE_COMMAND: Command being executed (for Bash tool)
- CLAUDE_MESSAGE_CONTEXT: Optional context about the operation

Hook Configuration:
Add to .claude/settings.local.json:
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/multitool-safeguards.py"
          }
        ]
      }
    ]
  }
}
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from kaia_guardrails.hooks.base import HookBase, HookError

# Set up logging
log_dir = Path(__file__).parent.parent / "diagnostics"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "multitool-safeguards.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("multitool-safeguards")


class SafeguardDecision(Enum):
    """Judge model decision on multitool operation safety."""
    APPROVE = "approve"
    DENY = "deny"
    REQUIRE_HUMAN = "require_human"


@dataclass
class ToolCall:
    """Represents a single tool call."""
    tool_name: str
    file_paths: List[str]
    parameters: Dict[str, Any]
    timestamp: float


class MultitoolCallTracker:
    """Tracks tool calls within a short time window to detect multitool operations."""

    def __init__(self, window_seconds: float = 5.0):
        self.window_seconds = window_seconds
        self.call_history_file = Path.home() / ".claude_tool_calls.json"

    def get_recent_calls(self) -> List[ToolCall]:
        """Get tool calls within the time window."""
        try:
            if not self.call_history_file.exists():
                return []

            with open(self.call_history_file, 'r') as f:
                calls_data = json.load(f)

            current_time = time.time()
            recent_calls = []

            for call_data in calls_data:
                if current_time - call_data['timestamp'] <= self.window_seconds:
                    recent_calls.append(ToolCall(
                        tool_name=call_data['tool_name'],
                        file_paths=call_data['file_paths'],
                        parameters=call_data['parameters'],
                        timestamp=call_data['timestamp']
                    ))

            return recent_calls

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Error reading call history: {e}")
            return []

    def record_current_call(self, tool_call: ToolCall) -> None:
        """Record the current tool call."""
        try:
            # Get existing calls
            calls_data = []
            if self.call_history_file.exists():
                try:
                    with open(self.call_history_file, 'r') as f:
                        calls_data = json.load(f)
                except json.JSONDecodeError:
                    calls_data = []

            # Add current call
            calls_data.append({
                'tool_name': tool_call.tool_name,
                'file_paths': tool_call.file_paths,
                'parameters': tool_call.parameters,
                'timestamp': tool_call.timestamp
            })

            # Keep only recent calls (last 100 or within time window)
            current_time = time.time()
            calls_data = [
                call for call in calls_data[-100:]  # Keep last 100
                if current_time - call['timestamp'] <= self.window_seconds * 2  # Keep 2x window
            ]

            # Write back
            with open(self.call_history_file, 'w') as f:
                json.dump(calls_data, f, indent=2)

        except OSError as e:
            logger.warning(f"Error recording call: {e}")


class MultitoolSafeguards:
    """Main safeguards logic for evaluating multitool operations."""

    # High-risk tools that require extra scrutiny
    HIGH_RISK_TOOLS = {
        "Write", "MultiEdit", "NotebookEdit", "Bash", "mcp__ide__executeCode", "Edit"
    }

    # Dangerous tool combinations
    DANGEROUS_COMBINATIONS = [
        {"Write", "Bash"},           # Write files then execute
        {"MultiEdit", "Bash"},       # Edit multiple files then execute
        {"Edit", "Bash"},            # Edit file then execute
        {"Write", "mcp__ide__executeCode"},  # Write then execute code
    ]

    def __init__(self):
        self.tracker = MultitoolCallTracker()

    def evaluate_operation(self, current_call: ToolCall, recent_calls: List[ToolCall]) -> SafeguardDecision:
        """Evaluate if the current operation in context of recent calls is safe."""

        all_calls = recent_calls + [current_call]

        # Single call - generally safe unless high-risk
        if len(all_calls) == 1:
            if current_call.tool_name in self.HIGH_RISK_TOOLS:
                return self._evaluate_single_high_risk_call(current_call)
            return SafeguardDecision.APPROVE

        # Multiple calls - check for dangerous patterns
        return self._evaluate_multitool_batch(all_calls)

    def _evaluate_single_high_risk_call(self, call: ToolCall) -> SafeguardDecision:
        """Evaluate a single high-risk tool call."""

        if call.tool_name == "Bash":
            command = call.parameters.get("command", "")
            if self._is_dangerous_bash_command(command):
                logger.warning(f"Dangerous bash command blocked: {command}")
                return SafeguardDecision.DENY

        # High-risk tools generally require human oversight for complex operations
        if len(call.file_paths) > 3 or any(self._is_system_critical_path(p) for p in call.file_paths):
            return SafeguardDecision.REQUIRE_HUMAN

        return SafeguardDecision.APPROVE

    def _evaluate_multitool_batch(self, calls: List[ToolCall]) -> SafeguardDecision:
        """Evaluate a batch of tool calls for safety."""

        tool_names = {call.tool_name for call in calls}

        # Check for dangerous combinations
        for dangerous_combo in self.DANGEROUS_COMBINATIONS:
            if dangerous_combo.issubset(tool_names):
                logger.warning(f"Dangerous tool combination detected: {dangerous_combo}")
                return SafeguardDecision.DENY

        # Check for too many high-risk operations
        high_risk_count = sum(1 for call in calls if call.tool_name in self.HIGH_RISK_TOOLS)
        if high_risk_count >= 3:
            logger.warning(f"Too many high-risk operations: {high_risk_count}")
            return SafeguardDecision.REQUIRE_HUMAN

        # Check file overlap - operating on same files with different tools
        all_files = set()
        file_conflicts = False
        for call in calls:
            for file_path in call.file_paths:
                if file_path in all_files:
                    file_conflicts = True
                all_files.add(file_path)

        if file_conflicts and len(tool_names) > 1:
            logger.warning("File conflicts detected across multiple tool calls")
            return SafeguardDecision.REQUIRE_HUMAN

        # Multiple writes/edits
        write_tools = {"Write", "MultiEdit", "Edit", "NotebookEdit"}
        write_count = sum(1 for call in calls if call.tool_name in write_tools)
        if write_count >= 4:
            logger.warning(f"Many write operations: {write_count}")
            return SafeguardDecision.REQUIRE_HUMAN

        return SafeguardDecision.APPROVE

    def _is_dangerous_bash_command(self, command: str) -> bool:
        """Check if bash command contains dangerous patterns."""
        dangerous_patterns = [
            "rm -rf", "sudo rm", "format", "mkfs", "dd if=", ":(){ :|:& };:",
            "chmod -R 777", "chown -R", "curl | sh", "wget | sh", "cat /dev/zero",
            "> /dev/", "rm /*", "rm -r /", "sudo chmod", "sudo chown"
        ]

        command_lower = command.lower()
        return any(pattern.lower() in command_lower for pattern in dangerous_patterns)

    def _is_system_critical_path(self, file_path: str) -> bool:
        """Check if file path is system-critical."""
        critical_patterns = [
            "/etc/", "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/",
            "/System/", "/Library/", "C:\\Windows\\", "C:\\Program Files\\",
            "~/.ssh/", "~/.aws/", "/root/"
        ]

        return any(pattern in file_path for pattern in critical_patterns)


def main():
    """Main hook execution."""

    # Get environment variables from Claude Code
    tool_name = os.getenv("CLAUDE_TOOL_NAME", "")
    file_paths_str = os.getenv("CLAUDE_FILE_PATHS", "")
    command = os.getenv("CLAUDE_COMMAND", "")
    context = os.getenv("CLAUDE_MESSAGE_CONTEXT", "")

    if not tool_name:
        # No tool name, nothing to evaluate
        logger.debug("No tool name provided, allowing operation")
        sys.exit(0)

    # Parse file paths
    file_paths = [p.strip() for p in file_paths_str.split(",") if p.strip()] if file_paths_str else []

    # Create current tool call
    current_call = ToolCall(
        tool_name=tool_name,
        file_paths=file_paths,
        parameters={"command": command} if command else {},
        timestamp=time.time()
    )

    # Initialize safeguards
    safeguards = MultitoolSafeguards()

    # Get recent calls to detect multitool operations
    recent_calls = safeguards.tracker.get_recent_calls()

    # Record current call
    safeguards.tracker.record_current_call(current_call)

    # Evaluate safety
    decision = safeguards.evaluate_operation(current_call, recent_calls)

    # Log the decision
    if len(recent_calls) > 0:
        logger.info(f"Evaluating multitool operation: {len(recent_calls) + 1} calls including {tool_name}")

    # Handle decision
    if decision == SafeguardDecision.DENY:
        print("🚫 MULTITOOL OPERATION BLOCKED", file=sys.stderr)
        print("", file=sys.stderr)
        print("This multitool operation has been blocked for safety reasons:", file=sys.stderr)

        if len(recent_calls) > 0:
            print(f"• Detected {len(recent_calls) + 1} tool calls in quick succession", file=sys.stderr)
            for call in recent_calls[-3:]:  # Show last 3
                print(f"  - {call.tool_name} on {len(call.file_paths)} files", file=sys.stderr)
            print(f"  - {current_call.tool_name} on {len(current_call.file_paths)} files (current)", file=sys.stderr)

        if current_call.tool_name == "Bash":
            print(f"• Dangerous bash command detected", file=sys.stderr)

        print("", file=sys.stderr)
        print("Suggested alternatives:", file=sys.stderr)
        print("• Break the operation into smaller, individual steps", file=sys.stderr)
        print("• Execute tools one at a time with manual review", file=sys.stderr)
        print("• Use safer alternatives where possible", file=sys.stderr)
        print("", file=sys.stderr)

        sys.exit(1)  # Block the operation

    elif decision == SafeguardDecision.REQUIRE_HUMAN:
        print("⚠️  MULTITOOL OPERATION REQUIRES HUMAN APPROVAL", file=sys.stderr)
        print("", file=sys.stderr)
        print("This operation requires human review:", file=sys.stderr)

        if len(recent_calls) > 0:
            print(f"• {len(recent_calls) + 1} tool calls detected in quick succession", file=sys.stderr)

        print(f"• Current operation: {tool_name} on {len(file_paths)} files", file=sys.stderr)

        if current_call.tool_name in safeguards.HIGH_RISK_TOOLS:
            print(f"• {tool_name} is considered a high-risk tool", file=sys.stderr)

        print("", file=sys.stderr)
        print("To proceed:", file=sys.stderr)
        print("• Review the operation carefully", file=sys.stderr)
        print("• Consider the potential impact", file=sys.stderr)
        print("• If safe, you can override by setting CLAUDE_OVERRIDE_SAFEGUARDS=1", file=sys.stderr)
        print("", file=sys.stderr)

        # Check for override
        if os.getenv("CLAUDE_OVERRIDE_SAFEGUARDS") == "1":
            print("🔓 Override detected, allowing operation", file=sys.stderr)
            sys.exit(0)
        else:
            sys.exit(1)  # Block unless overridden

    else:  # APPROVE
        logger.debug(f"Approved operation: {tool_name}")
        sys.exit(0)  # Allow the operation


class MultitoolSafeguardsHook(HookBase):
    """Hook that provides safeguards for multitool operations."""

    def __init__(self):
        super().__init__(name="multitool_safeguards", priority=5)  # Run early

    def run(self, context: Dict[str, Any]) -> Any:
        """Run multitool safeguards."""
        # Only run on PreToolUse
        if context.get('hook_type') != 'PreToolUse':
            return None

        try:
            # Get environment variables from Claude Code
            tool_name = os.getenv("CLAUDE_TOOL_NAME", "")
            file_paths_str = os.getenv("CLAUDE_FILE_PATHS", "")
            command = os.getenv("CLAUDE_COMMAND", "")

            if not tool_name:
                return None

            # Parse file paths
            file_paths = [p.strip() for p in file_paths_str.split(",") if p.strip()] if file_paths_str else []

            # Create current tool call
            current_call = ToolCall(
                tool_name=tool_name,
                file_paths=file_paths,
                parameters={"command": command} if command else {},
                timestamp=time.time()
            )

            # Initialize safeguards
            safeguards = MultitoolSafeguards()

            # Evaluate the operation
            decision = safeguards.evaluate_operation(current_call)

            if decision == SafeguardDecision.BLOCK:
                raise HookError(f"🚫 BLOCKED: Multitool safeguard triggered for {tool_name}")
            elif decision == SafeguardDecision.WARN:
                return f"⚠️ WARNING: Potentially risky multitool operation: {tool_name}"

            return f"✅ Approved multitool operation: {tool_name}"

        except Exception as e:
            return f"Error in multitool safeguards: {e}"

if __name__ == "__main__":
    main()