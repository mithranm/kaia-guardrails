#!/usr/bin/env python3
"""
Kaia Guardrails CLI Tools

Command-line interface for kaia-guardrails audit and management tools.
"""

import sys
import argparse
from pathlib import Path

from .audit_viewer import AuditLogViewer


def audit_command(args):
    """Handle the audit subcommand."""
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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Kaia Guardrails CLI Tools',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Audit command
    audit_parser = subparsers.add_parser('audit', help='Generate audit report from logs')
    audit_parser.add_argument('--date', help='Filter logs for specific date (YYYY-MM-DD)')
    audit_parser.add_argument('--hours', type=int, default=24, help='Time window in hours (default: 24)')
    audit_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    audit_parser.add_argument('--save', '-s', help='Save report to file')
    audit_parser.add_argument('--log-dir', help='Custom log directory path')
    audit_parser.add_argument('--project-root', help='Project root directory to search for logs')
    audit_parser.set_defaults(func=audit_command)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()