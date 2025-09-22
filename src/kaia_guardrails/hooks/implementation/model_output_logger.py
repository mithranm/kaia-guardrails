"""
Model Output Logger Hook

Logs all Claude Code model outputs and summarizes script execution in an easy to follow chain.
Integrates with qdrant chat ingester for structured logging and retrieval.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler

from kaia_guardrails.hooks.base import HookBase


class ModelOutputLoggerHook(HookBase):
    """Hook that logs all model outputs and script execution with qdrant integration."""

    def __init__(self):
        super().__init__(name="model_output_logger", priority=200)  # Run last to capture all context
        self.logger = None
        self.log_dir = None
        self.current_project_root = None  # Set during run() from context
        self.setup_logging()

    def setup_logging(self):
        """Set up rotating file handler for model output logging."""
        try:
            # Create dedicated log directory
            project_root = self._get_project_root()
            self.log_dir = project_root / '.claude' / 'logs' / 'model_outputs'
            self.log_dir.mkdir(parents=True, exist_ok=True)

            # Setup logger with rotating file handler
            self.logger = logging.getLogger('claude_model_outputs')
            self.logger.setLevel(logging.INFO)

            # Clear existing handlers
            self.logger.handlers.clear()

            # Create daily rotating file handler with date suffix
            current_date = datetime.now().strftime('%Y-%m-%d')
            log_file = self.log_dir / f'model_outputs_{current_date}.jsonl'

            # Use TimedRotatingFileHandler for daily rotation
            from logging.handlers import TimedRotatingFileHandler
            handler = TimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=7,  # Keep 7 days of logs
                encoding='utf-8'
            )

            # Custom formatter for structured JSON logging
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

            print(f"[MODEL-OUTPUT-LOGGER] Logging to: {log_file}")

        except Exception as e:
            print(f"[MODEL-OUTPUT-LOGGER-ERROR] Failed to setup logging: {e}")
            self.logger = None

    def run(self, context: Dict[str, Any]) -> Any:
        """Log model outputs and execution context."""
        if not self.logger:
            return None

        # Store project root from context for this run
        self.current_project_root = Path(context.get('cwd', os.getcwd()))

        try:
            hook_type = context.get('hook_type')
            tool_name = context.get('tool_name', 'unknown')

            # Skip logging for failed JSON parsing attempts (noise reduction)
            if hook_type == 'unknown' and tool_name in ['', 'unknown']:
                return None

            # Log different hook types with appropriate detail
            if hook_type == 'PreToolUse':
                return self._log_pre_tool_use(context)
            elif hook_type == 'PostToolUse':
                return self._log_post_tool_use(context)
            elif hook_type == 'UserPromptSubmit':
                return self._log_user_prompt(context)
            else:
                return self._log_general_event(context)

        except Exception as e:
            print(f"[MODEL-OUTPUT-LOGGER-ERROR] Logging failed: {e}")
            return None

    def _log_pre_tool_use(self, context: Dict[str, Any]) -> None:
        """Log pre-tool-use events with planning context."""
        tool_name = context.get('tool_name', 'unknown')
        tool_input = context.get('tool_input', {})

        # Create structured log entry for qdrant ingestion
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ansi_timestamp': self._get_ansi_timestamp(),
            'event_type': 'pre_tool_use',
            'friendly_process_name': f"Claude preparing {tool_name} operation",
            'tool_name': tool_name,
            'tool_input_summary': self._summarize_tool_input(tool_name, tool_input),
            'focus_context': self._get_focus_context(),
            'session_context': self._get_session_context(context),
            'metadata': {
                'hook_type': 'PreToolUse',
                'tool_operation': tool_name,
                'input_size': len(str(tool_input)),
                'files_involved': self._extract_file_paths(tool_input),
                'operation_complexity': self._assess_operation_complexity(tool_name, tool_input)
            }
        }

        self._write_log_entry(log_entry)

    def _log_post_tool_use(self, context: Dict[str, Any]) -> None:
        """Log post-tool-use events with results and impacts."""
        tool_name = context.get('tool_name', 'unknown')
        tool_input = context.get('tool_input', {})

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ansi_timestamp': self._get_ansi_timestamp(),
            'event_type': 'post_tool_use',
            'friendly_process_name': f"Claude completed {tool_name} operation",
            'tool_name': tool_name,
            'operation_result': self._analyze_operation_result(tool_name, tool_input),
            'focus_context': self._get_focus_context(),
            'git_context': self._get_git_context(),
            'session_context': self._get_session_context(context),
            'metadata': {
                'hook_type': 'PostToolUse',
                'tool_operation': tool_name,
                'files_modified': self._extract_file_paths(tool_input),
                'operation_success': True,  # Assume success if hook is running
                'commits_created': self._check_for_new_commits(),
                'execution_chain_step': self._get_execution_step_number()
            }
        }

        self._write_log_entry(log_entry)

    def _log_user_prompt(self, context: Dict[str, Any]) -> None:
        """Log user prompt submissions for conversation tracking."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ansi_timestamp': self._get_ansi_timestamp(),
            'event_type': 'user_prompt_submit',
            'friendly_process_name': "User submitted new prompt to Claude",
            'prompt_context': self._get_prompt_context(context),
            'conversation_context': self._get_conversation_context(),
            'focus_context': self._get_focus_context(),
            'metadata': {
                'hook_type': 'UserPromptSubmit',
                'prompt_length': len(context.get('prompt', '')),
                'conversation_turn': self._get_conversation_turn(),
                'active_focus_processes': self._count_active_focus_processes()
            }
        }

        self._write_log_entry(log_entry)

    def _log_general_event(self, context: Dict[str, Any]) -> None:
        """Log general hook events."""
        hook_type = context.get('hook_type', 'unknown')

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ansi_timestamp': self._get_ansi_timestamp(),
            'event_type': 'general_hook_event',
            'friendly_process_name': f"Claude hook event: {hook_type}",
            'hook_context': context,
            'metadata': {
                'hook_type': hook_type,
                'context_keys': list(context.keys()),
                'event_category': 'system'
            }
        }

        self._write_log_entry(log_entry)

    def _get_ansi_timestamp(self) -> str:
        """Get ANSI-formatted timestamp for better readability."""
        now = datetime.now()
        return f"\033[36m{now.strftime('%H:%M:%S')}\033[0m \033[90m{now.strftime('%Y-%m-%d')}\033[0m"

    def _get_focus_context(self) -> Dict[str, Any]:
        """Get current focus process context."""
        try:
            from .focus_process_manager import FocusProcessManager
            manager = FocusProcessManager()
            focus_info = manager.get_current_focus_info()

            return {
                'current_focus': focus_info.get('focus_id'),
                'focus_description': focus_info.get('description'),
                'stack_depth': focus_info.get('stack_depth', 0),
                'branch_name': focus_info.get('branch_name'),
                'auto_commit_enabled': focus_info.get('auto_commit', False)
            }
        except Exception:
            return {'error': 'Failed to get focus context'}

    def _get_git_context(self) -> Dict[str, Any]:
        """Get current git context."""
        try:
            import subprocess
            project_root = self._get_project_root()

            # Current branch
            result = subprocess.run(['git', 'branch', '--show-current'],
                                  capture_output=True, text=True, cwd=project_root)
            current_branch = result.stdout.strip() if result.returncode == 0 else 'unknown'

            # Latest commit
            result = subprocess.run(['git', 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True, cwd=project_root)
            latest_commit = result.stdout.strip()[:8] if result.returncode == 0 else 'unknown'

            return {
                'current_branch': current_branch,
                'latest_commit': latest_commit,
                'git_status': 'tracked'
            }
        except Exception:
            return {'error': 'Failed to get git context'}

    def _get_session_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get Claude Code session context."""
        return {
            'session_id': context.get('session_id', 'unknown'),
            'transcript_path': context.get('transcript_path', ''),
            'cwd': context.get('cwd', ''),
            'claude_input_keys': list(context.get('claude_input', {}).keys())
        }

    def _summarize_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Create a human-readable summary of tool input."""
        if tool_name == 'Write':
            file_path = tool_input.get('file_path', 'unknown')
            content_length = len(tool_input.get('content', ''))
            return f"Writing {content_length} characters to {Path(file_path).name}"

        elif tool_name == 'Edit':
            file_path = tool_input.get('file_path', 'unknown')
            old_len = len(tool_input.get('old_string', ''))
            new_len = len(tool_input.get('new_string', ''))
            return f"Editing {Path(file_path).name}: {old_len} -> {new_len} chars"

        elif tool_name == 'MultiEdit':
            file_path = tool_input.get('file_path', 'unknown')
            edit_count = len(tool_input.get('edits', []))
            return f"MultiEdit {Path(file_path).name}: {edit_count} changes"

        elif tool_name == 'Read':
            file_path = tool_input.get('file_path', 'unknown')
            return f"Reading {Path(file_path).name}"

        elif tool_name == 'Bash':
            command = tool_input.get('command', 'unknown')[:50]
            return f"Executing: {command}{'...' if len(command) == 50 else ''}"

        else:
            return f"{tool_name} operation with {len(tool_input)} parameters"

    def _analyze_operation_result(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Analyze the result/impact of a tool operation."""
        if tool_name in ['Write', 'Edit', 'MultiEdit']:
            files = self._extract_file_paths(tool_input)
            return f"Modified {len(files)} file(s): {', '.join(Path(f).name for f in files[:3])}"

        elif tool_name == 'Read':
            file_path = tool_input.get('file_path', 'unknown')
            return f"Read content from {Path(file_path).name}"

        elif tool_name == 'Bash':
            return "Command executed successfully"

        else:
            return f"{tool_name} completed successfully"

    def _extract_file_paths(self, tool_input: Dict[str, Any]) -> list:
        """Extract file paths from tool input."""
        paths = []

        if 'file_path' in tool_input and tool_input['file_path']:
            paths.append(tool_input['file_path'])

        if 'notebook_path' in tool_input and tool_input['notebook_path']:
            paths.append(tool_input['notebook_path'])

        return paths

    def _assess_operation_complexity(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Assess the complexity of the operation."""
        if tool_name == 'MultiEdit':
            edit_count = len(tool_input.get('edits', []))
            if edit_count > 10:
                return 'high'
            elif edit_count > 3:
                return 'medium'
            else:
                return 'low'

        elif tool_name == 'Write':
            content_length = len(tool_input.get('content', ''))
            if content_length > 5000:
                return 'high'
            elif content_length > 1000:
                return 'medium'
            else:
                return 'low'

        else:
            return 'low'

    def _check_for_new_commits(self) -> bool:
        """Check if new git commits were created."""
        # This would need integration with focus process manager
        # For now, return a placeholder
        return False

    def _get_execution_step_number(self) -> int:
        """Get the current step number in the execution chain."""
        # This could be maintained as a counter in the session
        # For now, return a placeholder
        return 1

    def _get_prompt_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get context about the user prompt."""
        return {
            'prompt_preview': str(context.get('prompt', ''))[:200] + '...',
            'prompt_type': 'user_input'
        }

    def _get_conversation_context(self) -> Dict[str, Any]:
        """Get conversation context."""
        return {
            'conversation_active': True,
            'context_window': 'active'
        }

    def _get_conversation_turn(self) -> int:
        """Get the current conversation turn number."""
        # This would need to be tracked across the session
        return 1

    def _count_active_focus_processes(self) -> int:
        """Count active focus processes."""
        try:
            from .focus_process_manager import FocusProcessManager
            manager = FocusProcessManager()
            focus_info = manager.get_current_focus_info()
            return focus_info.get('stack_depth', 0)
        except Exception:
            return 0

    def _get_project_root(self) -> Path:
        """Find the project root directory."""
        # Use project root from context if available, fallback to discovery
        if self.current_project_root:
            return self.current_project_root

        current = Path.cwd()
        while current.parent != current:
            if (current / '.git').exists():
                return current
            current = current.parent
        return Path.cwd()

    def _write_log_entry(self, entry: Dict[str, Any]) -> None:
        """Write a log entry to the main log file."""
        if self.logger:
            self.logger.info(json.dumps(entry, ensure_ascii=False))

