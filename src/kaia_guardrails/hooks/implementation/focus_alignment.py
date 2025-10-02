"""Focus alignment checker using vibelint LLM with structured output."""

import json
import os
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ..base import HookBase


class FocusCheck(BaseModel):
    """Schema for focus alignment check response."""

    aligned: bool = Field(description="True if action aligns with focus, False otherwise")


class FocusAlignmentHook(HookBase):
    """Checks if current action aligns with focus using vibelint LLM."""

    def __init__(self):
        super().__init__(name="focus_alignment", priority=15)

    def run(self, context: dict) -> dict:
        """Check if current action aligns with stated focus."""
        project_root = Path(context.get("project_root", Path.cwd()))
        focus_file = project_root / ".claude" / "current-focus.txt"
        skip_file = project_root / ".claude" / "skip-focus-check"

        # Skip if user disabled check
        if skip_file.exists():
            return {"status": "skipped", "reason": "check disabled by user"}

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

        # Read recent conversation history
        from ...conversation_reader import ConversationReader

        reader = ConversationReader()
        session = reader.read_session()  # Gets current session

        # Get last 5 messages for context (balance between context and token usage)
        recent_messages = []
        if session and session.messages:
            for msg in session.messages[-5:]:
                role = msg.role
                content_preview = msg.content[:300] if msg.content else ""
                recent_messages.append(f"{role}: {content_preview}")

        conversation_context = "\n".join(recent_messages) if recent_messages else "No recent conversation"

        # Build context for LLM
        action_context = f"Tool: {tool_name}\n"
        if user_prompt and hook_event == "UserPromptSubmit":
            action_context += f"User Request: {user_prompt}\n"
        elif tool_input:
            action_context += f"Action: {tool_input[:500]}\n"

        action_context += f"\nRecent Conversation:\n{conversation_context}"

        # Use vibelint LLM with structured output
        try:
            import json
            from dataclasses import asdict

            from vibelint.llm_client import LLMClient, LLMRequest

            client = LLMClient()

            # Set up log file for full request/response (for finetuning)
            log_dir = project_root / ".kaia-guardrails"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "focus-alignment-llm.jsonl"

            # Get Pydantic schema
            json_schema = FocusCheck.model_json_schema()

            prompt = f"""Current Focus: {current_focus}

Current Action:
{action_context}

Does this action align with the stated focus? Consider:
- Is this action moving toward the focus goal?
- Is this a necessary prerequisite or distraction?
- Would time spent on this help achieve the focus?"""

            request = LLMRequest(
                content=prompt,
                max_tokens=512,  # Enough for reasoning + JSON output
                temperature=0.1,  # Low temp for consistent decisions
                structured_output={"json_schema": {"name": "focus_check", "schema": json_schema}}
            )

            response = client.process_request_sync(request)

            # Log full request/response for finetuning (not just preview)
            full_log = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "request_content": prompt,  # Full prompt
                "request_tokens_estimate": len(prompt) // 3,  # 3 chars = 1 token
                "response_content": response.content,  # Full response
                "response_reasoning": response.reasoning_content,  # Thinking tokens
                "llm_used": response.llm_used,
                "duration_seconds": response.duration_seconds,
                "success": response.success,
            }
            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(full_log) + "\n")
            except Exception as e:
                print(f"Failed to write full LLM log: {e}", file=sys.stderr)

            # Parse structured response
            try:
                result = json.loads(response.content)
                aligned = result.get("aligned", True)  # Default to True on parse error

                # Get reasoning from thinking tokens
                reasoning = response.reasoning_content or "No reasoning provided"

                if not aligned:
                    # Misalignment detected - block action
                    print(f"\n⚠️ FOCUS DRIFT DETECTED - BLOCKING ACTION", file=sys.stderr)
                    print(f"📍 Current Focus: {current_focus}", file=sys.stderr)
                    print(f"🤔 Reasoning: {reasoning}", file=sys.stderr)
                    print(f"\n💡 To override:", file=sys.stderr)
                    print(f"   1. Update your focus: echo 'new focus' > .claude/current-focus.txt", file=sys.stderr)
                    print(f"   2. Or disable check: touch .claude/skip-focus-check\n", file=sys.stderr)

                    sys.exit(1)  # Block the action

                return {
                    "status": "success",
                    "aligned": aligned,
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
