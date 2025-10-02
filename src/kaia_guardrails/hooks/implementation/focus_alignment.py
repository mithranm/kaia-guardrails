"""Focus alignment checker using vibelint LLM with structured output."""

import json
import os
import sys
from pathlib import Path

from ..base import HookBase


class FocusAlignmentHook(HookBase):
    """Checks if current action aligns with focus using vibelint LLM."""

    def __init__(self):
        super().__init__(name="focus_alignment", priority=15)

    def run(self, context: dict) -> dict:
        """Check if current action aligns with stated focus."""
        project_root = Path(context.get("project_root", Path.cwd()))
        focus_file = project_root / ".claude" / "current-focus.txt"

        # Skip if no focus set
        if not focus_file.exists():
            return {"status": "skipped", "reason": "no focus file"}

        # Read current focus
        with open(focus_file) as f:
            current_focus = f.read().strip()

        if not current_focus:
            return {"status": "skipped", "reason": "focus file empty"}

        # Get current action context
        tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
        tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
        user_prompt = os.environ.get("CLAUDE_USER_PROMPT", "")
        hook_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")

        # Build context for LLM
        action_context = f"Tool: {tool_name}\n"
        if user_prompt and hook_event == "UserPromptSubmit":
            action_context += f"User Request: {user_prompt[:200]}\n"
        elif tool_input:
            action_context += f"Action: {tool_input[:200]}\n"

        # Use vibelint LLM with structured output
        try:
            from vibelint.llm_client import LLMClient, LLMRequest

            client = LLMClient()

            # Structured output schema for yes/no decision
            schema = {
                "type": "object",
                "properties": {
                    "aligned": {
                        "type": "boolean",
                        "description": "True if action aligns with focus, False otherwise"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confidence level 0-1"
                    }
                },
                "required": ["aligned", "confidence"],
                "additionalProperties": False
            }

            prompt = f"""Current Focus: {current_focus}

Current Action:
{action_context}

Does this action align with the stated focus? Consider:
- Is this action moving toward the focus goal?
- Is this a necessary prerequisite or distraction?
- Would time spent on this help achieve the focus?"""

            request = LLMRequest(
                content=prompt,
                max_tokens=50,
                temperature=0.1,  # Low temp for consistent decisions
                structured_output={"json_schema": {"schema": schema}}
            )

            response = client.process_request_sync(request)

            # Parse structured response
            try:
                result = json.loads(response.content)
                aligned = result.get("aligned", True)  # Default to True on parse error
                confidence = result.get("confidence", 0.5)

                # Get reasoning from thinking tokens
                reasoning = response.reasoning_content or "No reasoning provided"

                if not aligned and confidence > 0.7:
                    # High confidence misalignment - warn user
                    print(f"\n⚠️ FOCUS DRIFT DETECTED", file=sys.stderr)
                    print(f"📍 Current Focus: {current_focus}", file=sys.stderr)
                    print(f"🤔 Reasoning: {reasoning}", file=sys.stderr)
                    print(f"💡 Consider: Is this action aligned with your stated focus?\n", file=sys.stderr)

                    return {
                        "status": "warning",
                        "aligned": False,
                        "confidence": confidence,
                        "reasoning": reasoning
                    }

                return {
                    "status": "success",
                    "aligned": aligned,
                    "confidence": confidence,
                    "reasoning": reasoning
                }

            except json.JSONDecodeError:
                # Fallback if structured output fails
                return {"status": "error", "error": "Failed to parse LLM response"}

        except ImportError as e:
            # vibelint not available - warn loudly
            print(f"\n⚠️ FOCUS ALIGNMENT DISABLED", file=sys.stderr)
            print(f"❌ Cannot import vibelint LLM: {e}", file=sys.stderr)
            print(f"💡 Install vibelint to enable focus drift detection\n", file=sys.stderr)
            return {"status": "error", "error": f"vibelint import failed: {e}"}
        except Exception as e:
            # Other errors - warn loudly
            print(f"\n⚠️ FOCUS ALIGNMENT CHECK FAILED", file=sys.stderr)
            print(f"❌ Error: {e}", file=sys.stderr)
            print(f"💡 Check vibelint configuration\n", file=sys.stderr)
            return {"status": "error", "error": str(e)}
