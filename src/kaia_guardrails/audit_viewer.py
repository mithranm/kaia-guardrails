#!/usr/bin/env python3
"""
Kaia Guardrails Audit Log Viewer

Built-in audit viewer that parses the efficient model output logs into a human-readable view.
Shows model decisions, tool call patterns, hook interventions, and focus process interactions.
"""

import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import argparse


class AuditLogViewer:
    """Analyzes kaia-guardrails model output logs for audit purposes."""

    def __init__(self, log_dir: Optional[Path] = None, project_root: Optional[Path] = None):
        """
        Initialize audit viewer.

        Args:
            log_dir: Explicit log directory path
            project_root: Project root to search for logs (defaults to current working directory)
        """
        self.log_dir = log_dir or self._find_log_directory(project_root)

    def _find_log_directory(self, project_root: Optional[Path] = None) -> Path:
        """
        Find the kaia-guardrails log directory.

        Args:
            project_root: Starting directory for search (defaults to cwd)
        """
        start_dir = project_root or Path.cwd()

        # First, try the direct path in the specified project
        direct_path = start_dir / '.claude' / 'logs' / 'model_outputs'
        if direct_path.exists():
            return direct_path

        # Walk up the directory tree to find .claude/logs/model_outputs
        current = start_dir.resolve()
        while current.parent != current:
            log_dir = current / '.claude' / 'logs' / 'model_outputs'
            if log_dir.exists():
                return log_dir
            current = current.parent

        # If not found, check common locations
        common_locations = [
            Path.home() / '.claude' / 'logs' / 'model_outputs',  # User home
            Path('/tmp') / 'claude_logs' / 'model_outputs',       # System temp
            start_dir / 'logs' / 'model_outputs',                 # Project logs dir
        ]

        for location in common_locations:
            if location.exists():
                return location

        # Fallback - create in project root
        fallback_dir = start_dir / '.claude' / 'logs' / 'model_outputs'
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir

    def load_logs(self, date_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load and parse JSONL log entries.

        Args:
            date_filter: YYYY-MM-DD format to filter logs for specific date
        """
        entries = []

        if date_filter:
            log_files = [self.log_dir / f"model_outputs_{date_filter}.jsonl"]
        else:
            # Load all available log files
            log_files = sorted(self.log_dir.glob("model_outputs_*.jsonl"))

        for log_file in log_files:
            if not log_file.exists():
                continue

            try:
                with open(log_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        if line.strip():
                            try:
                                entry = json.loads(line)
                                entry['_source_file'] = log_file.name
                                entry['_line_number'] = line_num
                                entries.append(entry)
                            except json.JSONDecodeError as e:
                                print(f"Warning: Failed to parse {log_file}:{line_num}: {e}")
                                continue
            except FileNotFoundError:
                print(f"Log file not found: {log_file}")
                continue

        return sorted(entries, key=lambda x: x.get('timestamp', ''))

    def analyze_decision_patterns(self, entries: List[Dict[str, Any]], time_window_hours: int = 24) -> Dict[str, Any]:
        """Analyze patterns in Claude's decision making within a time window."""

        # Filter to time window if specified
        if time_window_hours and entries:
            cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
            cutoff_str = cutoff_time.isoformat()
            entries = [e for e in entries if e.get('timestamp', '') >= cutoff_str]

        tool_sequences = []
        current_sequence = []
        hook_interventions = []
        focus_interactions = []
        llm_decisions = []
        quality_gates = []

        for entry in entries:
            event_type = entry.get('event_type')
            tool_name = entry.get('tool_name', '')
            timestamp = entry.get('timestamp', '')

            if event_type == 'pre_tool_use':
                tool_call = {
                    'tool': tool_name,
                    'timestamp': timestamp,
                    'input_summary': entry.get('tool_input_summary', ''),
                    'complexity': entry.get('metadata', {}).get('operation_complexity', 'unknown'),
                    'focus_context': entry.get('focus_context', {}),
                    'session_id': entry.get('session_context', {}).get('session_id', 'unknown')
                }
                current_sequence.append(tool_call)

            elif event_type == 'post_tool_use':
                if current_sequence:
                    # Complete the sequence
                    last_tool = current_sequence[-1]
                    last_tool['success'] = entry.get('metadata', {}).get('operation_success', False)
                    last_tool['files_modified'] = entry.get('metadata', {}).get('files_modified', [])
                    last_tool['commits_created'] = entry.get('metadata', {}).get('commits_created', False)

                    # Check for hook interventions
                    result = entry.get('operation_result', '')
                    if any(keyword in result.lower() for keyword in ['blocked', 'override', 'quality gate', 'intervention']):
                        hook_interventions.append({
                            'tool': tool_name,
                            'timestamp': timestamp,
                            'intervention_type': self._classify_intervention(result),
                            'details': result,
                            'session_id': entry.get('session_context', {}).get('session_id', 'unknown')
                        })

                    # Check for quality gates
                    if 'quality gate' in result.lower() or 'violation' in result.lower():
                        quality_gates.append({
                            'tool': tool_name,
                            'timestamp': timestamp,
                            'gate_type': self._extract_gate_type(result),
                            'details': result
                        })

            elif event_type == 'user_prompt_submit':
                # End current sequence and start new one
                if current_sequence:
                    tool_sequences.append({
                        'sequence': current_sequence,
                        'session_id': current_sequence[0].get('session_id', 'unknown'),
                        'started_at': current_sequence[0].get('timestamp'),
                        'ended_at': current_sequence[-1].get('timestamp') if len(current_sequence) > 1 else current_sequence[0].get('timestamp')
                    })
                    current_sequence = []

            # Track focus interactions
            focus_context = entry.get('focus_context', {})
            if focus_context and 'error' not in str(focus_context):
                focus_interactions.append({
                    'timestamp': timestamp,
                    'event': event_type,
                    'context': focus_context,
                    'tool': tool_name
                })

        # Add final sequence
        if current_sequence:
            tool_sequences.append({
                'sequence': current_sequence,
                'session_id': current_sequence[0].get('session_id', 'unknown'),
                'started_at': current_sequence[0].get('timestamp'),
                'ended_at': current_sequence[-1].get('timestamp') if len(current_sequence) > 1 else current_sequence[0].get('timestamp')
            })

        return {
            'time_window_hours': time_window_hours,
            'entries_analyzed': len(entries),
            'tool_sequences': tool_sequences,
            'hook_interventions': hook_interventions,
            'focus_interactions': focus_interactions,
            'quality_gates': quality_gates,
            'llm_decisions': llm_decisions
        }

    def _classify_intervention(self, result: str) -> str:
        """Classify the type of hook intervention."""
        result_lower = result.lower()
        if 'blocked' in result_lower:
            return 'BLOCKED'
        elif 'override' in result_lower:
            return 'OVERRIDE'
        elif 'quality gate' in result_lower:
            return 'QUALITY_GATE'
        elif 'auto-fix' in result_lower:
            return 'AUTO_FIX'
        else:
            return 'OTHER'

    def _extract_gate_type(self, result: str) -> str:
        """Extract quality gate type from result."""
        if 'emoji' in result.lower():
            return 'emoji_check'
        elif 'git' in result.lower():
            return 'git_operations'
        elif 'focus' in result.lower():
            return 'focus_process'
        else:
            return 'unknown'

    def generate_audit_report(self, analysis: Dict[str, Any], verbose: bool = False) -> str:
        """Generate a human-readable audit report."""

        report = []
        report.append("=" * 90)
        report.append("🔍 KAIA GUARDRAILS AUDIT REPORT")
        report.append("=" * 90)
        report.append(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"⏱️  Time window: {analysis['time_window_hours']} hours")
        report.append(f"📊 Entries analyzed: {analysis['entries_analyzed']}")
        report.append("")

        # Executive Summary
        report.append("📋 EXECUTIVE SUMMARY")
        report.append("-" * 50)
        report.append(f"  Tool sequences executed: {len(analysis['tool_sequences'])}")
        report.append(f"  Hook interventions: {len(analysis['hook_interventions'])}")
        report.append(f"  Quality gate violations: {len(analysis['quality_gates'])}")
        report.append(f"  Focus process interactions: {len(analysis['focus_interactions'])}")
        report.append("")

        # Hook Interventions Analysis
        if analysis['hook_interventions']:
            report.append("🛡️ HOOK INTERVENTIONS")
            report.append("-" * 50)

            intervention_counts = {}
            for intervention in analysis['hook_interventions']:
                int_type = intervention['intervention_type']
                intervention_counts[int_type] = intervention_counts.get(int_type, 0) + 1

            report.append("Intervention types:")
            for int_type, count in sorted(intervention_counts.items()):
                report.append(f"  {int_type}: {count} times")
            report.append("")

            if verbose:
                report.append("Detailed interventions:")
                for intervention in analysis['hook_interventions'][-10:]:  # Last 10
                    report.append(f"  ⚠️  [{intervention['timestamp'][:19]}] {intervention['tool']} - {intervention['intervention_type']}")
                    report.append(f"      {intervention['details'][:100]}...")
                report.append("")

        else:
            report.append("🛡️ HOOK INTERVENTIONS: ⚠️ NONE DETECTED")
            report.append("-" * 50)
            report.append("  🚨 This suggests hooks may not be properly blocking operations")
            report.append("  🚨 LLM-based decision making hooks may not be configured")
            report.append("  🚨 This explains why the LLM didn't interfere with operations")
            report.append("")

        # Quality Gates
        if analysis['quality_gates']:
            report.append("🚧 QUALITY GATES")
            report.append("-" * 50)

            gate_counts = {}
            for gate in analysis['quality_gates']:
                gate_type = gate['gate_type']
                gate_counts[gate_type] = gate_counts.get(gate_type, 0) + 1

            for gate_type, count in sorted(gate_counts.items()):
                report.append(f"  {gate_type}: {count} violations")
            report.append("")

        # Tool Usage Patterns
        report.append("🔧 TOOL USAGE PATTERNS")
        report.append("-" * 50)

        tool_counts = {}
        success_rates = {}

        for seq_info in analysis['tool_sequences']:
            for tool_call in seq_info['sequence']:
                tool = tool_call['tool']
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

                success = tool_call.get('success', True)
                if tool not in success_rates:
                    success_rates[tool] = {'success': 0, 'total': 0}
                success_rates[tool]['total'] += 1
                if success:
                    success_rates[tool]['success'] += 1

        report.append("Tool usage frequency and success rates:")
        for tool, count in sorted(tool_counts.items(), key=lambda x: x[1], reverse=True):
            success_rate = (success_rates[tool]['success'] / success_rates[tool]['total']) * 100 if tool in success_rates else 100
            report.append(f"  {tool}: {count} times ({success_rate:.1f}% success)")
        report.append("")

        # Focus Process Analysis
        if analysis['focus_interactions']:
            report.append("🎯 FOCUS PROCESS ANALYSIS")
            report.append("-" * 50)
            report.append(f"  Active focus interactions: {len(analysis['focus_interactions'])}")

            if verbose:
                for interaction in analysis['focus_interactions'][-5:]:  # Last 5
                    report.append(f"  📍 [{interaction['timestamp'][:19]}] {interaction['event']} - {interaction['tool']}")
            report.append("")
        else:
            report.append("🎯 FOCUS PROCESS ANALYSIS: ⚠️ NO ACTIVE FOCUS CONTEXT")
            report.append("-" * 50)
            report.append("  🚨 Focus context shows 'Failed to get focus context' errors")
            report.append("  🚨 Focus process manager may not be integrated with hooks")
            report.append("")

        # Recommendations
        report.append("💡 RECOMMENDATIONS")
        report.append("-" * 50)

        if not analysis['hook_interventions']:
            report.append("  🔧 CRITICAL: Configure LLM-based decision hooks")
            report.append("     - Add hooks that can analyze code changes and block dangerous operations")
            report.append("     - Implement semantic analysis hooks for better decision making")

        if not analysis['focus_interactions']:
            report.append("  🔧 HIGH: Fix focus process integration")
            report.append("     - Ensure focus process manager is properly loaded in hook context")
            report.append("     - Debug 'Failed to get focus context' errors")

        if analysis['quality_gates']:
            report.append("  🔧 MEDIUM: Review quality gate violations")
            report.append("     - Consider implementing auto-fix mechanisms")
            report.append("     - Adjust quality gate sensitivity if needed")

        report.append("")
        report.append("=" * 90)

        return "\n".join(report)

    def save_report(self, report: str, filename: Optional[str] = None) -> Path:
        """Save audit report to file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"kaia_audit_report_{timestamp}.txt"

        output_path = self.log_dir / filename
        with open(output_path, 'w') as f:
            f.write(report)

        return output_path


def main():
    parser = argparse.ArgumentParser(description='Kaia Guardrails Audit Log Viewer')
    parser.add_argument('--date', help='Filter logs for specific date (YYYY-MM-DD)')
    parser.add_argument('--hours', type=int, default=24, help='Time window in hours (default: 24)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--save', '-s', help='Save report to file')
    parser.add_argument('--log-dir', help='Custom log directory path')
    parser.add_argument('--project-root', help='Project root directory to search for logs')

    args = parser.parse_args()

    # Initialize viewer
    log_dir = Path(args.log_dir) if args.log_dir else None
    project_root = Path(args.project_root) if args.project_root else None
    viewer = AuditLogViewer(log_dir=log_dir, project_root=project_root)

    print("🔍 Loading kaia-guardrails logs...")
    entries = viewer.load_logs(args.date)

    if not entries:
        print("❌ No log entries found.")
        sys.exit(1)

    print(f"📊 Analyzing {len(entries)} log entries...")
    analysis = viewer.analyze_decision_patterns(entries, args.hours)

    print("📋 Generating audit report...")
    report = viewer.generate_audit_report(analysis, args.verbose)

    print(report)

    # Save report if requested
    if args.save:
        output_path = viewer.save_report(report, args.save)
        print(f"\n📄 Report saved to: {output_path}")


if __name__ == "__main__":
    main()