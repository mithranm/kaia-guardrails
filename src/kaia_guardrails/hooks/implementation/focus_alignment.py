"""Focus alignment checker using vibelint LLM with structured output."""

import json
import os
import sys
import time
from pathlib import Path

from enum import Enum

from pydantic import BaseModel, Field

from ..base import HookBase


class AlignmentStatus(str, Enum):
    """Alignment status for focus check."""

    ALIGNED = "aligned"
    NOT_ALIGNED = "not_aligned"
    NEEDS_CONTEXT = "needs_context"


class FocusCheck(BaseModel):
    """Schema for focus alignment check response."""

    status: AlignmentStatus = Field(
        description="aligned if action aligns with focus, not_aligned if it doesn't, needs_context if more context needed to decide"
    )


class FocusAlignmentHook(HookBase):
    """Checks if current action aligns with focus using vibelint LLM."""

    def __init__(self):
        super().__init__(
            name="focus_alignment",
            priority=15,
            events=["PreToolUse", "UserPromptSubmit"]  # Only check BEFORE actions
        )

    def run(self, context: dict) -> dict:
        """Check if current action aligns with stated focus."""
        hook_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")

        project_root = Path(context.get("project_root", Path.cwd()))
        focus_file = project_root / ".claude" / "current-focus.txt"
        skip_file = project_root / ".claude" / "skip-focus-check"

        print(f"[Focus Check] Starting check for event: {hook_event}", file=sys.stderr)

        # Skip if user disabled check
        if skip_file.exists():
            print(f"[Focus Check] Skipped: check disabled by user", file=sys.stderr)
            return {"status": "skipped", "reason": "check disabled by user"}

        # Skip if no focus set
        if not focus_file.exists():
            print(f"[Focus Check] Skipped: no focus file at {focus_file}", file=sys.stderr)
            return {"status": "skipped", "reason": "no focus file"}

        # Read current focus
        with open(focus_file) as f:
            current_focus = f.read().strip()

        if not current_focus:
            print(f"[Focus Check] Skipped: focus file empty", file=sys.stderr)
            return {"status": "skipped", "reason": "focus file empty"}

        # Get current action context
        tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
        tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
        user_prompt = os.environ.get("CLAUDE_USER_PROMPT", "")
        hook_event = os.environ.get("CLAUDE_HOOK_EVENT_NAME", "")

        # Build minimal context for fast check (keep under 1024 tokens = ~3000 chars)
        action_context_minimal = f"Event: {hook_event}\n"
        if user_prompt and hook_event == "UserPromptSubmit":
            action_context_minimal += f"User: {user_prompt[:200]}\n"
        elif tool_name:
            action_context_minimal += f"Tool: {tool_name}\n"
            if tool_input:
                action_context_minimal += f"Input: {tool_input[:200]}\n"

        # Debug: Log what hook event we're processing
        print(f"[Focus Check] Event: {hook_event}, Tool: {tool_name}", file=sys.stderr)

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

            # PHASE 1: Fast check with minimal context (prioritize speed)
            fast_prompt = f"""Focus: {current_focus}

Action: {action_context_minimal}

Does this align with focus? Respond "aligned", "not_aligned", or "needs_context" (if you need conversation history/AGENTS to decide)."""

            fast_request = LLMRequest(
                content=fast_prompt,
                max_tokens=100,  # Minimal for fast response
                temperature=0.1,
                structured_output={"json_schema": {"name": "focus_check", "schema": json_schema}}
            )

            print("[Focus Check] Phase 1: Fast check...", file=sys.stderr)
            fast_response = client.process_request_sync(fast_request)

            # Log fast check
            fast_log = {
                "phase": "fast",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "request_content": fast_prompt,
                "request_tokens_estimate": len(fast_prompt) // 3,
                "response_content": fast_response.content,
                "response_reasoning": fast_response.reasoning_content,
                "llm_used": fast_response.llm_used,
                "duration_seconds": fast_response.duration_seconds,
            }
            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(fast_log) + "\n")
            except Exception as e:
                print(f"Failed to write fast check log: {e}", file=sys.stderr)

            # Parse fast response
            fast_result = json.loads(fast_response.content)
            fast_status = fast_result.get("status")

            # If fast LLM is confident, use its decision
            if fast_status in ("aligned", "not_aligned"):
                print(f"[Focus Check] Fast decision: {fast_status}", file=sys.stderr)
                response = fast_response
            else:
                # PHASE 2: Escalate to orchestrator with full context
                print("[Focus Check] Phase 2: Escalating to orchestrator (needs context)...", file=sys.stderr)

                # Gather full context
                from ...conversation_reader import ConversationReader
                from ...utils import read_all_agents_content

                reader = ConversationReader()
                session = reader.read_session()

                # Get last 5 messages
                recent_messages = []
                if session and session.messages:
                    for msg in session.messages[-5:]:
                        role = msg.role
                        content_preview = msg.content[:300] if msg.content else ""
                        recent_messages.append(f"{role}: {content_preview}")

                conversation_context = "\n".join(recent_messages) if recent_messages else "No conversation"

                # Read AGENTS files
                agents_content = read_all_agents_content(project_root)
                agents_summary = agents_content[:500] if agents_content else "No AGENTS files"

                # Full context
                action_context_full = f"Event: {hook_event}\n"
                if user_prompt and hook_event == "UserPromptSubmit":
                    action_context_full += f"User Request: {user_prompt}\n"
                elif tool_name:
                    action_context_full += f"Tool: {tool_name}\n"
                    if tool_input:
                        action_context_full += f"Tool Input: {tool_input[:500]}\n"
                action_context_full += f"\nRecent Conversation:\n{conversation_context}"

                full_prompt = f"""Focus: {current_focus}

AGENTS (first 500 chars): {agents_summary}

Action: {action_context_full}

Does this align with focus AND comply with AGENTS? Respond "aligned" or "not_aligned"."""

                full_request = LLMRequest(
                    content=full_prompt,
                    max_tokens=512,
                    temperature=0.1,
                    structured_output={"json_schema": {"name": "focus_check", "schema": json_schema}}
                )

                response = client.process_request_sync(full_request)

            # Log full request/response for finetuning (not just preview)
            # Determine which prompt was actually used (fast or full)
            actual_prompt = full_prompt if fast_status == "needs_context" else fast_prompt
            full_log = {
                "phase": "full" if fast_status == "needs_context" else "fast",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "request_content": actual_prompt,  # Full prompt
                "request_tokens_estimate": len(actual_prompt) // 3,  # 3 chars = 1 token
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
                status = result.get("status", "aligned")  # Default to aligned on parse error

                # Get reasoning from thinking tokens
                reasoning = response.reasoning_content or "No reasoning provided"

                if status == "not_aligned":
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
                    "aligned": status == "aligned",
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
