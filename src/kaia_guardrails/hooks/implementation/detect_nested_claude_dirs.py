#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Detect nested .claude directories hook.

Scans for .claude directories nested within the project to prevent
configuration conflicts and sync issues. Warns about potential problems
and suggests cleanup actions.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from kaia_guardrails.hooks.base import HookBase, HookError

def get_project_root() -> Path:
    """Find the project root (where the main .claude directory should be)."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.claude').exists() and (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

def find_nested_claude_dirs(root_path: Path) -> List[Dict[str, Any]]:
    """Find all nested .claude directories using fast find command."""
    import subprocess

    nested_claudes = []
    main_claude = root_path / '.claude'

    try:
        # Use find command for much faster directory search
        result = subprocess.run(
            ['find', str(root_path), '-type', 'd', '-name', '.claude'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line:
                    claude_path = Path(line)

                    # Skip the main .claude directory
                    if claude_path == main_claude:
                        continue

                    relative_path = claude_path.relative_to(root_path)
                    parent_dir = claude_path.parent

                    # Gather information about this nested .claude
                    info = {
                        'path': str(claude_path),
                        'relative_path': str(relative_path),
                        'parent_directory': str(parent_dir.name),
                        'has_settings': (claude_path / 'settings.local.json').exists(),
                        'has_hooks': (claude_path / 'hooks').exists(),
                        'hook_count': 0,
                        'potential_issues': []
                    }

                    # Count hooks if hooks directory exists
                    if info['has_hooks']:
                        hooks_dir = claude_path / 'hooks'
                        try:
                            info['hook_count'] = len([f for f in hooks_dir.iterdir()
                                                   if f.is_file() and f.suffix == '.py'])
                        except OSError:
                            info['hook_count'] = 0

                    # Identify potential issues
                    if info['has_settings']:
                        info['potential_issues'].append('duplicate_settings')

                    if info['has_hooks'] and info['hook_count'] > 0:
                        info['potential_issues'].append('duplicate_hooks')

                    # Special cases
                    if 'node_modules' in str(parent_dir):
                        info['potential_issues'].append('node_modules_claude')
                    elif 'venv' in str(parent_dir) or 'env' in str(parent_dir):
                        info['potential_issues'].append('virtual_env_claude')

                    nested_claudes.append(info)

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        # Fallback to empty result if find fails
        pass

    return nested_claudes

def categorize_issues(nested_claudes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize nested .claude directories by severity."""
    categories = {
        'critical': [],      # Definitely problematic
        'warning': [],       # Potentially problematic
        'informational': []  # Probably benign but worth noting
    }

    for claude_info in nested_claudes:
        issues = claude_info['potential_issues']

        if any(issue in issues for issue in ['duplicate_settings', 'duplicate_hooks']):
            categories['critical'].append(claude_info)
        elif any(issue in issues for issue in ['node_modules_claude', 'git_directory_claude']):
            categories['warning'].append(claude_info)
        else:
            categories['informational'].append(claude_info)

    return categories

def generate_cleanup_suggestions(categorized: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Generate specific cleanup suggestions."""
    suggestions = []

    for claude_info in categorized['critical']:
        path = claude_info['relative_path']
        parent = claude_info['parent_directory']

        if claude_info['has_settings']:
            suggestions.append(f"🔥 Remove {path}/settings.local.json - conflicts with main settings")

        if claude_info['has_hooks'] and claude_info['hook_count'] > 0:
            suggestions.append(f"🔥 Move hooks from {path}/hooks/ to main .claude/hooks/ directory")
            suggestions.append(f"   Then remove {path}/hooks/ directory")

        suggestions.append(f"🔥 Consider removing entire {path} directory")

    for claude_info in categorized['warning']:
        path = claude_info['relative_path']

        if 'node_modules_claude' in claude_info['potential_issues']:
            suggestions.append(f"⚠️  {path} is in node_modules - likely from package, safe to ignore")

        if 'git_directory_claude' in claude_info['potential_issues']:
            suggestions.append(f"⚠️  {path} is in .git directory - investigate why it's there")

        if 'virtual_env_claude' in claude_info['potential_issues']:
            suggestions.append(f"⚠️  {path} is in virtual environment - likely from package installation")

    return suggestions

def should_block_operation(categorized: Dict[str, List[Dict[str, Any]]]) -> bool:
    """Determine if we should block operations due to critical .claude conflicts."""
    # Block if there are multiple .claude directories with settings or hooks
    critical_count = len(categorized['critical'])
    return critical_count > 0

def save_detection_results(nested_claudes: List[Dict[str, Any]], categorized: Dict[str, List[Dict[str, Any]]]):
    """Save detection results for debugging and tracking."""
    project_root = get_project_root()
    results_dir = project_root / '.claude' / 'diagnostics'
    results_dir.mkdir(exist_ok=True)

    results = {
        'timestamp': datetime.now().isoformat(),
        'total_nested_claudes': len(nested_claudes),
        'categorized_results': categorized,
        'detailed_findings': nested_claudes
    }

    results_file = results_dir / 'nested-claude-detection.json'
    import json
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

def main():
    """Main detection function."""
    try:
        project_root = get_project_root()

        # Find all nested .claude directories
        nested_claudes = find_nested_claude_dirs(project_root)

        if not nested_claudes:
            print("✅ No nested .claude directories found")
            return  # No nested .claude directories found - all good!

        # Categorize by severity
        categorized = categorize_issues(nested_claudes)

        # Generate cleanup suggestions
        suggestions = generate_cleanup_suggestions(categorized)

        # Save results
        save_detection_results(nested_claudes, categorized)

        # Report findings
        print("🔍 Nested .claude Directory Detection Results:")
        print(f"Found {len(nested_claudes)} nested .claude director{'ies' if len(nested_claudes) != 1 else 'y'}")

        if categorized['critical']:
            print(f"\n🔥 CRITICAL ISSUES ({len(categorized['critical'])} found):")
            for claude_info in categorized['critical']:
                print(f"  - {claude_info['relative_path']}")
                if claude_info['has_settings']:
                    print(f"    ⚠️  Has settings.local.json (conflicts with main config)")
                if claude_info['has_hooks']:
                    print(f"    ⚠️  Has {claude_info['hook_count']} hook files")

        if categorized['warning']:
            print(f"\n⚠️  WARNINGS ({len(categorized['warning'])} found):")
            for claude_info in categorized['warning']:
                print(f"  - {claude_info['relative_path']} (in {claude_info['parent_directory']})")

        if categorized['informational']:
            print(f"\nℹ️  INFORMATIONAL ({len(categorized['informational'])} found):")
            for claude_info in categorized['informational']:
                print(f"  - {claude_info['relative_path']}")

        # Show cleanup suggestions
        if suggestions:
            print(f"\n🛠️  CLEANUP SUGGESTIONS:")
            for suggestion in suggestions:
                print(f"  {suggestion}")

        # Determine if we should block
        should_block = should_block_operation(categorized)

        if should_block:
            print(f"\n🚫 BLOCKING OPERATION - Critical .claude configuration conflicts detected!")
            print(f"Please resolve the critical issues above before proceeding.")
            print(f"\nQuick fix commands:")
            for claude_info in categorized['critical']:
                print(f"  rm -rf {claude_info['path']}")
            print(f"\nThen move any needed hooks to main .claude/hooks/ directory")
            sys.exit(1)  # Block the operation

        elif categorized['warning']:
            print(f"\n⚠️  Warnings detected but not blocking. Consider cleanup when convenient.")

    except Exception as e:
        # Don't block on hook errors - just log them
        project_root = get_project_root()
        error_log = project_root / '.claude' / 'diagnostics' / 'nested-claude-errors.log'
        error_log.parent.mkdir(exist_ok=True)

        with open(error_log, 'a') as f:
            f.write(f"{datetime.now().isoformat()}: {str(e)}\n")

        # Optionally print error in development
        if os.environ.get('CLAUDE_HOOK_DEBUG'):
            print(f"Error in nested .claude detection: {e}")

class DetectNestedClaudeDirsHook(HookBase):
    """Hook that detects nested .claude directories to prevent conflicts."""

    def __init__(self):
        super().__init__(name="detect_nested_claude_dirs", priority=20)

    def run(self, context: Dict[str, Any]) -> Any:
        """Detect nested .claude directories."""
        try:
            # Use project root from context instead of cwd()
            project_root = Path(context.get('cwd', os.getcwd()))
            nested_claudes = find_nested_claude_dirs(project_root)

            if not nested_claudes:
                return "✅ No nested .claude directories found"

            # Categorize by severity
            categorized = categorize_issues(nested_claudes)
            save_detection_results(nested_claudes, categorized)

            # Return warning for critical issues
            if categorized['critical']:
                warnings = []
                for claude_info in categorized['critical']:
                    warnings.append(f"Critical: {claude_info['relative_path']}")
                return f"⚠️ Found {len(categorized['critical'])} critical nested .claude dirs: {', '.join(warnings)}"

            return f"⚠️ Found {len(nested_claudes)} nested .claude directories"

        except Exception as e:
            return f"Error detecting nested .claude dirs: {e}"

if __name__ == '__main__':
    main()