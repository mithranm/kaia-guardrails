#!/usr/bin/env python3
"""
Conversation History Ingester for Flashback System

Processes model output logs and ingests them into Qdrant for semantic similarity search.
Uses internal network hosts and applies proven RAG chunking strategies.
"""
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Generator
import argparse

from hooks.implementation.conversation_flashback_system import ConversationFlashbackSystem


class ConversationHistoryIngester:
    """Ingests conversation history from model output logs into Qdrant."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logs_dir = project_root / '.claude' / 'logs' / 'model_outputs'
        self.flashback_system = ConversationFlashbackSystem()

    def process_recent_logs(self, days_back: int = 7) -> int:
        """Process recent model output logs and ingest to Qdrant."""
        print(f"[INGESTER] Processing logs from last {days_back} days...")

        # Ensure Qdrant collection exists
        if not self.flashback_system.ensure_qdrant_collection():
            print("[INGESTER-ERROR] Failed to ensure Qdrant collection")
            return 0

        processed_count = 0
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Find log files within date range
        log_files = self._find_recent_log_files(cutoff_date)

        for log_file in log_files:
            print(f"[INGESTER] Processing: {log_file.name}")
            conversations = self._extract_conversations_from_log(log_file)

            for conversation in conversations:
                success = self.flashback_system.ingest_conversation_to_qdrant(
                    conversation['content'],
                    conversation['metadata']
                )
                if success:
                    processed_count += 1

        print(f"[INGESTER] Successfully processed {processed_count} conversation segments")
        return processed_count

    def _find_recent_log_files(self, cutoff_date: datetime) -> List[Path]:
        """Find model output log files within the date range."""
        log_files = []

        if not self.logs_dir.exists():
            print(f"[INGESTER-ERROR] Logs directory not found: {self.logs_dir}")
            return log_files

        for log_file in self.logs_dir.glob("model_outputs_*.jsonl"):
            try:
                # Extract date from filename (format: model_outputs_YYYY-MM-DD.jsonl)
                date_str = log_file.stem.split('_')[-1]  # Get the date part
                file_date = datetime.strptime(date_str, '%Y-%m-%d')

                if file_date >= cutoff_date:
                    log_files.append(log_file)

            except (ValueError, IndexError) as e:
                print(f"[INGESTER-WARNING] Could not parse date from {log_file.name}: {e}")

        return sorted(log_files)

    def _extract_conversations_from_log(self, log_file: Path) -> Generator[Dict[str, Any], None, None]:
        """
        Extract meaningful conversation segments from model output logs.
        Groups related operations and focuses on engineering contexts.
        """
        conversation_buffer = []
        current_focus_context = None

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Extract relevant information
                        timestamp = entry.get('timestamp', '')
                        event_type = entry.get('event_type', '')
                        tool_name = entry.get('tool_name', '')
                        focus_context = entry.get('focus_context', {})

                        # Update current focus context
                        if focus_context and 'description' in focus_context:
                            current_focus_context = focus_context['description']

                        # Look for meaningful engineering operations
                        if self._is_meaningful_operation(entry):
                            conversation_buffer.append({
                                'timestamp': timestamp,
                                'content': self._extract_content_from_entry(entry),
                                'tool_name': tool_name,
                                'focus_context': current_focus_context or 'General operation'
                            })

                        # Yield conversation segments when buffer reaches good size
                        if len(conversation_buffer) >= 10:  # 10 operations = good conversation segment
                            yield self._create_conversation_segment(conversation_buffer)
                            conversation_buffer = conversation_buffer[-2:]  # Keep some overlap

                    except (json.JSONDecodeError, KeyError) as e:
                        # Skip malformed entries
                        continue

            # Process remaining buffer
            if conversation_buffer:
                yield self._create_conversation_segment(conversation_buffer)

        except Exception as e:
            print(f"[INGESTER-ERROR] Failed to process {log_file}: {e}")

    def _is_meaningful_operation(self, entry: Dict[str, Any]) -> bool:
        """Determine if a log entry represents a meaningful engineering operation."""
        tool_name = entry.get('tool_name', '')
        event_type = entry.get('event_type', '')

        # Focus on operations that show engineering intent
        meaningful_tools = ['Edit', 'Write', 'MultiEdit', 'Read', 'Bash', 'Grep', 'Glob']

        # Include user prompts as they show engineering direction
        if event_type == 'user_prompt':
            return True

        # Include tool operations that modify or analyze code
        if tool_name in meaningful_tools:
            return True

        return False

    def _extract_content_from_entry(self, entry: Dict[str, Any]) -> str:
        """Extract meaningful content from a log entry."""
        content_parts = []

        # Add tool operation summary
        tool_name = entry.get('tool_name', '')
        if tool_name:
            content_parts.append(f"Operation: {tool_name}")

        # Add file context if available
        metadata = entry.get('metadata', {})
        files_involved = metadata.get('files_involved', [])
        if files_involved:
            content_parts.append(f"Files: {', '.join(files_involved[:3])}")  # First 3 files

        # Add operation summary
        operation_summary = entry.get('tool_input_summary', '') or entry.get('friendly_process_name', '')
        if operation_summary:
            content_parts.append(f"Summary: {operation_summary}")

        # Add focus context if available
        focus_context = entry.get('focus_context', {})
        if focus_context and 'description' in focus_context:
            content_parts.append(f"Focus: {focus_context['description']}")

        return " | ".join(content_parts)

    def _create_conversation_segment(self, buffer: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a conversation segment from buffer of operations."""
        if not buffer:
            return {}

        # Combine all operation content
        content_parts = []
        engineering_patterns = set()

        for operation in buffer:
            content_parts.append(operation['content'])

            # Extract engineering patterns
            if 'Edit' in operation['content'] or 'Write' in operation['content']:
                engineering_patterns.add('code_modification')
            if 'Bash' in operation['content']:
                engineering_patterns.add('command_execution')
            if 'Read' in operation['content'] or 'Grep' in operation['content']:
                engineering_patterns.add('code_analysis')

        # Create rich metadata
        first_op = buffer[0]
        last_op = buffer[-1]

        return {
            'content': '\n'.join(content_parts),
            'metadata': {
                'timestamp': first_op['timestamp'],
                'focus_context': first_op['focus_context'],
                'engineering_pattern': ', '.join(engineering_patterns) if engineering_patterns else 'general',
                'operation_count': len(buffer),
                'time_span': f"{first_op['timestamp']} to {last_op['timestamp']}"
            }
        }


def main():
    """Main entry point for the conversation history ingester."""
    parser = argparse.ArgumentParser(description='Ingest conversation history for flashback system')
    parser.add_argument('--days', type=int, default=7, help='Number of days back to process (default: 7)')
    parser.add_argument('--project-root', type=str, help='Project root directory (auto-detected if not provided)')

    args = parser.parse_args()

    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root)
    else:
        # Auto-detect project root by looking for .claude directory
        current = Path.cwd()
        while current.parent != current:
            if (current / '.claude').exists():
                project_root = current
                break
            current = current.parent
        else:
            project_root = Path.cwd()

    print(f"[INGESTER] Using project root: {project_root}")

    # Run ingestion
    ingester = ConversationHistoryIngester(project_root)
    processed_count = ingester.process_recent_logs(args.days)

    print(f"[INGESTER] Ingestion complete! Processed {processed_count} conversation segments.")
    print(f"[INGESTER] Flashback system ready for semantic similarity searches.")


if __name__ == "__main__":
    main()