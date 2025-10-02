"""
Claude Code Conversation Transcript Reader

Reads conversation transcripts from Claude Code's .jsonl files.
Provides access to current session messages, tool usage, and context.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Message:
    """Represents a message in the conversation."""

    role: str  # "user" or "assistant"
    content: str  # Text content
    timestamp: datetime
    message_id: str
    tool_uses: list[dict[str, Any]]  # Tool calls in this message


@dataclass
class SessionInfo:
    """Information about the current Claude Code session."""

    session_id: str
    transcript_path: Path
    cwd: Path
    git_branch: str | None
    messages: list[Message]


class ConversationReader:
    """Reads Claude Code conversation transcripts."""

    def __init__(self, project_root: Path | None = None):
        """Initialize reader.

        Args:
            project_root: Project root directory (defaults to cwd)
        """
        self.project_root = project_root or Path.cwd()
        self.claude_dir = Path.home() / ".claude"
        self.projects_dir = self.claude_dir / "projects"

    def get_current_session_id(self) -> str | None:
        """Get current session ID from environment or latest logs.

        Returns:
            Session ID if found, None otherwise
        """
        # Try environment variable (set by hooks)
        session_id = os.environ.get("CLAUDE_SESSION_ID")
        if session_id:
            return session_id

        # Try reading from latest model output log
        logs_dir = self.project_root / ".claude" / "logs" / "model_outputs"
        if not logs_dir.exists():
            return None

        # Get most recent log file
        log_files = sorted(logs_dir.glob("model_outputs_*.jsonl"), reverse=True)
        if not log_files:
            return None

        # Read last line to get session_id
        with open(log_files[0]) as f:
            for line in f:
                pass  # Get to last line
            try:
                data = json.loads(line)
                return data.get("session_context", {}).get("session_id")
            except (json.JSONDecodeError, KeyError):
                return None

    def get_transcript_path(self, session_id: str | None = None) -> Path | None:
        """Get transcript file path for session.

        Args:
            session_id: Session ID (defaults to current session)

        Returns:
            Path to transcript file, or None if not found
        """
        if not session_id:
            session_id = self.get_current_session_id()
            if not session_id:
                return None

        # Find project directory
        project_name = str(self.project_root).replace("/", "-")
        project_dir = self.projects_dir / project_name

        if not project_dir.exists():
            return None

        # Find transcript file by session ID
        transcript_file = project_dir / f"{session_id}.jsonl"
        if transcript_file.exists():
            return transcript_file

        return None

    def get_latest_transcript_path(self) -> Path | None:
        """Get the most recently modified transcript for this project.

        Returns:
            Path to latest transcript file, or None if not found
        """
        project_name = str(self.project_root).replace("/", "-")
        project_dir = self.projects_dir / project_name

        if not project_dir.exists():
            return None

        # Get all .jsonl files, sorted by modification time (newest first)
        transcript_files = sorted(
            project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )

        return transcript_files[0] if transcript_files else None

    def read_session(self, session_id: str | None = None) -> SessionInfo | None:
        """Read full conversation session.

        Args:
            session_id: Session ID (defaults to current/latest session)

        Returns:
            SessionInfo with messages, or None if not found
        """
        # Get transcript path
        if session_id:
            transcript_path = self.get_transcript_path(session_id)
        else:
            # Try current session first, fallback to latest
            transcript_path = self.get_transcript_path()
            if not transcript_path:
                transcript_path = self.get_latest_transcript_path()

        if not transcript_path:
            return None

        messages = []
        session_info = {
            "session_id": transcript_path.stem,  # Filename is session_id
            "cwd": self.project_root,
            "git_branch": None,
        }

        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Extract session metadata
                    if "cwd" in entry:
                        session_info["cwd"] = Path(entry["cwd"])
                    if "gitBranch" in entry:
                        session_info["git_branch"] = entry["gitBranch"]

                    # Extract messages
                    if entry.get("type") == "message":
                        message_data = entry["message"]
                        role = message_data["role"]

                        # Extract text content
                        text_parts = []
                        tool_uses = []

                        for content_block in message_data.get("content", []):
                            if content_block["type"] == "text":
                                text_parts.append(content_block["text"])
                            elif content_block["type"] == "tool_use":
                                tool_uses.append(content_block)

                        messages.append(
                            Message(
                                role=role,
                                content="\n".join(text_parts),
                                timestamp=datetime.fromisoformat(
                                    entry["timestamp"].replace("Z", "+00:00")
                                ),
                                message_id=message_data["id"],
                                tool_uses=tool_uses,
                            )
                        )

                except (json.JSONDecodeError, KeyError):
                    # Skip malformed entries
                    continue

        return SessionInfo(
            session_id=session_info["session_id"],
            transcript_path=transcript_path,
            cwd=session_info["cwd"],
            git_branch=session_info["git_branch"],
            messages=messages,
        )

    def get_recent_messages(self, count: int = 10, session_id: str | None = None) -> list[Message]:
        """Get recent messages from conversation.

        Args:
            count: Number of recent messages to retrieve
            session_id: Session ID (defaults to current/latest session)

        Returns:
            List of recent messages (newest first)
        """
        session = self.read_session(session_id)
        if not session:
            return []

        return session.messages[-count:][::-1]  # Last N messages, reversed

    def search_messages(
        self, query: str, case_sensitive: bool = False, session_id: str | None = None
    ) -> list[Message]:
        """Search for messages containing query string.

        Args:
            query: Search string
            case_sensitive: Whether to match case
            session_id: Session ID (defaults to current/latest session)

        Returns:
            List of matching messages
        """
        session = self.read_session(session_id)
        if not session:
            return []

        if not case_sensitive:
            query = query.lower()

        matches = []
        for msg in session.messages:
            content = msg.content if case_sensitive else msg.content.lower()
            if query in content:
                matches.append(msg)

        return matches

    def get_user_requirements(self, session_id: str | None = None) -> str:
        """Extract user requirements from conversation.

        Looks for user messages that appear to be requirements/specifications.

        Args:
            session_id: Session ID (defaults to current/latest session)

        Returns:
            Concatenated user requirements text
        """
        session = self.read_session(session_id)
        if not session:
            return ""

        requirements = []
        for msg in session.messages:
            if msg.role == "user":
                # Filter out short commands/questions
                if len(msg.content) > 50:  # Heuristic: longer messages are likely requirements
                    requirements.append(msg.content)

        return "\n\n---\n\n".join(requirements)


# CLI-friendly functions for killeraiagent
def get_current_conversation() -> SessionInfo | None:
    """Get current conversation session.

    Returns:
        SessionInfo for current session, or None if not found
    """
    reader = ConversationReader()
    return reader.read_session()


def search_conversation(query: str) -> list[Message]:
    """Search current conversation for query.

    Args:
        query: Search string

    Returns:
        List of matching messages
    """
    reader = ConversationReader()
    return reader.search_messages(query)


def get_requirements_from_conversation() -> str:
    """Extract requirements from current conversation.

    Returns:
        User requirements text
    """
    reader = ConversationReader()
    return reader.get_user_requirements()
