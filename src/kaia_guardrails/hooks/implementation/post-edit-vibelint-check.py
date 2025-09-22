#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Post-edit vibelint check hook.

Uses vibelint-safe to prevent API breakage, but maintains blocking behavior
for critical quality issues by checking if the original vibelint would have failed.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def get_project_root() -> Path:
    """Find the vibelint project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / 'pyproject.toml').exists() and 'vibelint' in current.name:
            return current
        current = current.parent
    return Path.cwd()

def run_vibelint_check_safe():
    """Run vibelint check using safe wrapper and parse results."""
    project_root = get_project_root()
    safe_wrapper = project_root / '.claude' / 'vibelint-safe'
    
    try:
        result = subprocess.run([
            str(safe_wrapper), 'check', 'src/', '--format', 'json', '--max-issues', '50'
        ], cwd=project_root, capture_output=True, text=True, timeout=60,
           env={**os.environ, 'PYTHONPATH': str(project_root / 'src')})
        
        # Parse vibelint-safe output to determine what happened
        tool_failed = False
        vibelint_found_issues = False
        issues_data = {'issues': [], 'summary': {'total_issues': 0}}
        
        # Check stderr for vibelint-safe status
        if result.stderr:
            if 'VIBELINT-SAFE-ERROR' in result.stderr:
                tool_failed = True
            elif 'VIBELINT-SAFE-WARN' in result.stderr:
                vibelint_found_issues = True
                # Try to extract returncode from JSON
                if 'original_would_have_failed": true' in result.stderr:
                    vibelint_found_issues = True
        
        # Try to parse JSON output
        if result.stdout.strip():
            try:
                issues_data = json.loads(result.stdout)
                if issues_data.get('issues'):
                    vibelint_found_issues = True
            except json.JSONDecodeError:
                # Not JSON, but might contain issue information
                if any(pattern in result.stdout.lower() for pattern in 
                       ['error', 'violation', 'issue', 'warning']):
                    vibelint_found_issues = True
        
        return {
            'tool_failed': tool_failed,
            'vibelint_found_issues': vibelint_found_issues,
            'issues_data': issues_data,
            'raw_stdout': result.stdout,
            'raw_stderr': result.stderr
        }
        
    except subprocess.TimeoutExpired:
        return {
            'tool_failed': True,
            'vibelint_found_issues': False,
            'issues_data': {'error': 'timeout'},
            'raw_stdout': '',
            'raw_stderr': 'Vibelint check timed out'
        }
    except Exception as e:
        return {
            'tool_failed': True,
            'vibelint_found_issues': False,
            'issues_data': {'error': str(e)},
            'raw_stdout': '',
            'raw_stderr': f'Error running vibelint: {e}'
        }

def should_block_for_critical_issues(check_result) -> bool:
    """
    Determine if we should block based on critical issues (GUARDRAIL).
    Only blocks if vibelint actually found issues, not if the tool failed.
    """
    if check_result['tool_failed'] and not check_result['vibelint_found_issues']:
        return False  # Don't block on tool failures
    
    if not check_result['vibelint_found_issues']:
        return False  # No issues found
    
    issues_data = check_result['issues_data']
    if 'error' in issues_data:
        return False  # Tool error, not validation issues
    
    issue_list = issues_data.get('issues', [])
    if not issue_list:
        return False
    
    # Count critical issues
    security_issues = 0
    architectural_issues = 0
    dead_code_count = 0
    
    for issue in issue_list:
        rule = issue.get('rule', '').lower()
        message = issue.get('message', '').lower()
        
        if any(keyword in rule or keyword in message for keyword in
               ['security', 'unsafe', 'vulnerability']):
            security_issues += 1
        elif any(keyword in rule or keyword in message for keyword in
                 ['architecture', 'coupling', 'dependency']):
            architectural_issues += 1
        elif any(keyword in rule or keyword in message for keyword in
                 ['unused', 'dead', 'unreachable']):
            dead_code_count += 1
    
    # Block on critical issues (GUARDRAIL)
    return security_issues > 0 or architectural_issues > 0 or dead_code_count > 10

def generate_summary(check_result) -> str:
    """Generate human-readable summary."""
    if check_result['tool_failed'] and not check_result['vibelint_found_issues']:
        return f"❌ Vibelint tool failed: {check_result['raw_stderr']}"
    
    if not check_result['vibelint_found_issues']:
        return "✅ No vibelint issues detected"
    
    issues_data = check_result['issues_data']
    if 'error' in issues_data:
        return f"❌ Vibelint error: {issues_data.get('message', 'Unknown error')}"
    
    issue_list = issues_data.get('issues', [])
    if not issue_list:
        return "✅ No vibelint issues detected"
    
    total_issues = len(issue_list)
    return f"⚠️  Found {total_issues} vibelint issue{'s' if total_issues != 1 else ''}"

def save_analysis(check_result, blocked: bool):
    """Save analysis for progress tracking."""
    try:
        project_root = get_project_root()
        analysis_dir = project_root / '.vibelint-progress'
        analysis_dir.mkdir(exist_ok=True)

        analysis_data = {
            'timestamp': datetime.now().isoformat(),
            'tool_name': os.environ.get('CLAUDE_TOOL_NAME', 'unknown'),
            'target_files': os.environ.get('CLAUDE_FILE_PATHS', '').split(','),
            'vibelint_result': check_result,
            'blocked': blocked
        }

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        analysis_file = analysis_dir / f'post-edit-analysis-{timestamp}.json'
        with open(analysis_file, 'w') as f:
            json.dump(analysis_data, f, indent=2)

        # Keep only last 10 files
        analysis_files = sorted(analysis_dir.glob('post-edit-analysis-*.json'))
        for old_file in analysis_files[:-10]:
            old_file.unlink()
    except Exception as e:
        print(f"[POST-EDIT-VIBELINT-ERROR] Failed to save analysis: {e}", file=sys.stderr)

def main():
    """Main post-edit vibelint check function."""
    # Only run after code edits
    tool_name = os.environ.get('CLAUDE_TOOL_NAME', '').lower()
    edit_tools = ['edit', 'patch', 'write', 'insert']
    if not any(edit_tool in tool_name for edit_tool in edit_tools):
        return

    print(f"[POST-EDIT-VIBELINT] Running check after {tool_name}", file=sys.stderr)

    # Run vibelint check using safe wrapper
    check_result = run_vibelint_check_safe()

    # Determine if we should block (GUARDRAIL) - only for actual vibelint issues
    should_block = should_block_for_critical_issues(check_result)

    # Generate summary
    summary = generate_summary(check_result)

    # Save analysis
    save_analysis(check_result, should_block)

    # Report results
    print(f"[POST-EDIT-VIBELINT] {summary}", file=sys.stderr)

    if check_result['tool_failed'] and not check_result['vibelint_found_issues']:
        # Tool execution failed - warn but don't block
        print("[POST-EDIT-VIBELINT] Tool execution failed, allowing operation", file=sys.stderr)
    elif should_block:
        # Critical vibelint issues found - block (GUARDRAIL)
        print("\n🚫 BLOCKING FURTHER ACTIONS - Critical vibelint issues detected!", file=sys.stderr)
        print("Please address critical security or architectural violations before proceeding.", file=sys.stderr)
        if check_result['raw_stdout']:
            print("\nVibelint output:", file=sys.stderr)
            print(check_result['raw_stdout'], file=sys.stderr)
        sys.exit(1)  # INTENTIONALLY BLOCKING - code quality guardrail
    elif check_result['vibelint_found_issues']:
        # Non-critical issues found - warn but don't block
        print("[POST-EDIT-VIBELINT] Issues detected but not critical, allowing operation", file=sys.stderr)
    else:
        # All good
        print("[POST-EDIT-VIBELINT] No issues detected", file=sys.stderr)

if __name__ == '__main__':
    main()
