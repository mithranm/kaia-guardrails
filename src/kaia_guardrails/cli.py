#!/usr/bin/env python3
"""
Kaia Guardrails CLI Tools

Command-line interface for kaia-guardrails audit and management tools.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from .audit_viewer import AuditLogViewer


def get_default_hook_config():
    """Get default hook configuration for settings.local.json."""
    return {
        "enabled": True,
        "implementations": {
            "post_edit_vibelint_check": {
                "enabled": True,
                "priority": 50,
                "config": {"block_on_critical": True, "auto_fix": False},
            },
            "agents_compliance_judge": {
                "enabled": True,
                "priority": 40,
                "config": {
                    "llm_endpoint": "${KAIA_JUDGE_LLM_URL}",
                    "llm_model": "${KAIA_JUDGE_LLM_MODEL}",
                },
            },
            "file_insertion_validator": {"enabled": True, "priority": 60},
            "git_operations_guard": {
                "enabled": True,
                "priority": 30,
                "config": {
                    "block_force_push": True,
                    "require_approval_for": ["push", "force-push", "rebase"],
                },
            },
            "pre_edit_validation": {"enabled": True, "priority": 10},
        },
    }


def install_command(args):
    """Install kaia-guardrails hooks into a project."""
    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    print(f"📦 Installing kaia-guardrails to {project_root}")

    # 1. Create .claude directory
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    print(f"  ✅ Created {claude_dir}")

    # 2. Create hooks directory and orchestrator
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # Find kaia-guardrails installation path
    kaia_pkg_path = Path(__file__).parent.parent.parent  # Go up to package root

    # Create orchestrator script that calls kaia-guardrails hooks
    orchestrator_content = f'''#!/usr/bin/env python3
"""
Orchestrator hook for kaia-guardrails.

Calls hooks from the kaia-guardrails package - hooks stay in the package
so you get updates automatically when you update kaia-guardrails.
"""

import sys
from pathlib import Path

# Add kaia-guardrails to Python path if not already installed
project_root = Path(__file__).resolve().parents[1]

try:
    from kaia_guardrails.hooks.orchestrator import Orchestrator

    # Run hooks from kaia-guardrails package (not copied locally)
    orchestrator = Orchestrator()

    context = {{
        "project_root": str(project_root),
        "working_directory": str(Path.cwd()),
    }}

    results = orchestrator.run_all(initial_context=context)

    # Check for critical failures
    critical_failures = []
    for hook_name, result in results["results"].items():
        if result["status"] in ["error", "crash"]:
            critical_failures.append((hook_name, result))

    if critical_failures:
        print("❌ Critical guardrail hooks failed:", file=sys.stderr)
        for hook_name, result in critical_failures:
            print(f"  - {{hook_name}}: {{result.get('error', 'Unknown error')}}", file=sys.stderr)
        sys.exit(1)

    print("✅ Kaia-guardrails hooks completed successfully")

except ImportError as e:
    print(f"❌ Failed to import kaia-guardrails: {{e}}", file=sys.stderr)
    print("Install with: pip install kaia-guardrails", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"❌ Orchestrator failed: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''

    orchestrator_path = hooks_dir / "orchestrator"
    with open(orchestrator_path, "w") as f:
        f.write(orchestrator_content)
    orchestrator_path.chmod(0o755)  # Make executable
    print(f"  ✅ Created orchestrator script")

    # 3. Create/update settings.local.json
    settings_file = claude_dir / "settings.local.json"
    if settings_file.exists():
        print(f"  ⚠️  {settings_file.name} exists, merging configuration...")
        with open(settings_file) as f:
            settings = json.load(f)
    else:
        settings = {}

    # Register orchestrator with Claude Code hook events
    if "hooks" not in settings:
        settings["hooks"] = {}

    # Register on UserPromptSubmit event (runs when user submits a message)
    if "UserPromptSubmit" not in settings["hooks"]:
        settings["hooks"]["UserPromptSubmit"] = []

    # Check if orchestrator already registered
    orchestrator_cmd = str(hooks_dir / "orchestrator")
    already_registered = any(
        hook.get("command") == orchestrator_cmd
        for hook_group in settings["hooks"].get("UserPromptSubmit", [])
        for hook in hook_group.get("hooks", [])
    )

    if not already_registered:
        settings["hooks"]["UserPromptSubmit"].append({
            "hooks": [
                {
                    "type": "command",
                    "command": orchestrator_cmd,
                    "timeout": 30
                }
            ]
        })
        print(f"  ✅ Registered orchestrator for UserPromptSubmit event")

    # Prompt for LLM configuration if not set
    if not settings.get("env", {}).get("KAIA_JUDGE_LLM_URL"):
        print("\n🤖 LLM Configuration (for agents_compliance_judge hook)")
        llm_url = (
            input("  LLM API URL [http://localhost:8000]: ").strip()
            or "http://localhost:8000"
        )
        llm_model = (
            input("  LLM Model [Qwen/Qwen2.5-7B-Instruct]: ").strip()
            or "Qwen/Qwen2.5-7B-Instruct"
        )

        if "env" not in settings:
            settings["env"] = {}
        settings["env"]["KAIA_JUDGE_LLM_URL"] = llm_url
        settings["env"]["KAIA_JUDGE_LLM_MODEL"] = llm_model

    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"  ✅ Updated {settings_file.name}")

    # 4. Python project checks
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        print("\n🐍 Python project detected")

        # Check vibelint installation
        try:
            import vibelint

            print(f"  ✅ vibelint found (v{vibelint.__version__})")
        except ImportError:
            print("  ⚠️  vibelint not installed")
            print("     Install: pip install vibelint")

        # Check vibelint config
        with open(pyproject) as f:
            content = f.read()
            if "[tool.vibelint]" not in content:
                print("  ⚠️  No [tool.vibelint] section in pyproject.toml")
                print("     Add minimal config:")
                print("     [tool.vibelint]")
                print('     include_globs = ["**/*.py"]')
                print('     exclude_globs = ["**/__pycache__/**", "**/.*"]')
            else:
                print("  ✅ vibelint configured in pyproject.toml")

    print("\n✅ Installation complete!")
    print("\n📋 Next steps:")
    print("  1. Review .claude/settings.local.json")
    print("  2. For Python projects: ensure vibelint is installed and configured")
    print("  3. Restart Claude Code to load hooks")


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
        description="Kaia Guardrails CLI Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    install_parser = subparsers.add_parser(
        "install", help="Install kaia-guardrails hooks into a project"
    )
    install_parser.add_argument(
        "project_root", nargs="?", help="Project root directory (default: current directory)"
    )
    install_parser.set_defaults(func=install_command)

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Generate audit report from logs")
    audit_parser.add_argument("--date", help="Filter logs for specific date (YYYY-MM-DD)")
    audit_parser.add_argument(
        "--hours", type=int, default=24, help="Time window in hours (default: 24)"
    )
    audit_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    audit_parser.add_argument("--save", "-s", help="Save report to file")
    audit_parser.add_argument("--log-dir", help="Custom log directory path")
    audit_parser.add_argument("--project-root", help="Project root directory to search for logs")
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
