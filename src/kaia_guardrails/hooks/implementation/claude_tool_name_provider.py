"""
Claude Tool Name Provider Hook

Ensures CLAUDE_TOOL_NAME environment variable is set for compliance assessments.
Extracts tool name from hook context and sets environment variable.
"""

import os
from typing import Any, Dict

from kaia_guardrails.hooks.base import HookBase


class ClaudeToolNameProviderHook(HookBase):
 """Hook that provides CLAUDE_TOOL_NAME environment variable for compliance."""

 def __init__(self):
 super().__init__(name="claude_tool_name_provider", priority=1) # Run first

 def run(self, context: Dict[str, Any]) -> Any:
 """Set CLAUDE_TOOL_NAME environment variable from context."""
 # Only run on PreToolUse to set the variable before other hooks
 if context.get("hook_type") != "PreToolUse":
 return None

 try:
 tool_name = context.get("tool_name")

 if tool_name:
 # Set environment variable for compliance assessments
 os.environ["CLAUDE_TOOL_NAME"] = tool_name

 # Also set some additional context that might be useful
 tool_input = context.get("tool_input", {})
 if tool_input:
 # Store serialized tool input for compliance context
 import json
 try:
 tool_input_str = json.dumps(tool_input, default=str)
 # Truncate if too long to avoid environment variable limits
 if len(tool_input_str) > 1000:
 tool_input_str = tool_input_str[:1000] + "..."
 os.environ["CLAUDE_TOOL_INPUT"] = tool_input_str
 except Exception:
 # If serialization fails, just set a placeholder
 os.environ["CLAUDE_TOOL_INPUT"] = f"<{tool_name}_input>"

 # Set hook type for compliance
 hook_type = context.get("hook_type", "unknown")
 os.environ["CLAUDE_HOOK_TYPE"] = hook_type

 return f"Set CLAUDE_TOOL_NAME={tool_name}"

 return None

 except Exception as e:
 # Don't block operations if this fails
 print(f"[CLAUDE-TOOL-NAME-ERROR] Failed to set tool name: {e}")
 return None