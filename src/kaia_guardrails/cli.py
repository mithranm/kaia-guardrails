#!/usr/bin/env python3
"""
Kaia Guardrails CLI Tools

Command-line interface for kaia-guardrails focus tracking installation.
"""

import argparse
import json
import sys
from pathlib import Path


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
    # Use #!/usr/bin/env python3 to find python in PATH (works across systems)
    orchestrator_content = '''#!/usr/bin/env python3
"""
Orchestrator hook for kaia-guardrails.

Calls hooks from the kaia-guardrails package - hooks stay in the package
so you get updates automatically when you update kaia-guardrails.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]

try:
    from kaia_guardrails.hooks.orchestrator import Orchestrator

    # Run hooks from kaia-guardrails package (not copied locally)
    orchestrator = Orchestrator()

    context = {
        "project_root": str(project_root),
        "working_directory": str(Path.cwd()),
    }

    results = orchestrator.run_all(initial_context=context)

    # Check for critical failures
    critical_failures = []
    for hook_name, result in results["results"].items():
        if result["status"] in ["error", "crash"]:
            critical_failures.append((hook_name, result))

    if critical_failures:
        print("❌ Critical guardrail hooks failed:", file=sys.stderr)
        for hook_name, result in critical_failures:
            print(f"  - {hook_name}: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    print("✅ Kaia-guardrails hooks completed successfully")

except ImportError as e:
    print(f"❌ Failed to import kaia-guardrails: {e}", file=sys.stderr)
    print("Install with: pip install kaia-guardrails", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"❌ Orchestrator failed: {e}", file=sys.stderr)
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

    orchestrator_cmd = str(hooks_dir / "orchestrator")

    # Register on multiple events
    hook_events = {
        "PreToolUse": 10,      # Short timeout, runs before every tool
        "PostToolUse": 30,     # Longer timeout, validation after tools
        "UserPromptSubmit": 30 # Runs when user submits message
    }

    for event_name, timeout in hook_events.items():
        if event_name not in settings["hooks"]:
            settings["hooks"][event_name] = []

        # Check if orchestrator already registered for this event
        already_registered = any(
            hook.get("command") == orchestrator_cmd
            for hook_group in settings["hooks"].get(event_name, [])
            for hook in hook_group.get("hooks", [])
        )

        if not already_registered:
            settings["hooks"][event_name].append({
                "hooks": [
                    {
                        "type": "command",
                        "command": orchestrator_cmd,
                        "timeout": timeout
                    }
                ]
            })
            print(f"  ✅ Registered orchestrator for {event_name}")

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
    print("  1. Create .claude/current-focus.txt with your current task")
    print("  2. Review .claude/settings.local.json")
    print("  3. For Python projects: ensure vibelint is installed and configured")
    print("  4. Restart Claude Code to load hooks")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Kaia Guardrails - Focus tracking for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    install_parser = subparsers.add_parser(
        "install", help="Install kaia-guardrails focus tracking hooks"
    )
    install_parser.add_argument(
        "project_root", nargs="?", help="Project root directory (default: current directory)"
    )
    install_parser.set_defaults(func=install_command)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
