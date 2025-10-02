"""
Vibelint Safe Mode Wrapper

A wrapper that ensures vibelint never exits with non-zero codes or causes
API breakage with Claude Code. Uses the vibelint API directly for clean integration.

Features:
- Never exits with error codes (always returns results)
- Direct API integration (no subprocess overhead)
- Exception handling for all vibelint operations
- Reports to Claude via structured output
- Clean library usage pattern
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import vibelint API - handle import errors gracefully
try:
    import os
    # Ensure vibelint is in Python path
    vibelint_path = "/Users/briyamanick/GitHub/killeraiagent/tools/vibelint/src"
    if vibelint_path not in sys.path:
        sys.path.insert(0, vibelint_path)

    from vibelint.api import VibelintAPI, check_files, validate_single_file, run_project_justification
    VIBELINT_AVAILABLE = True
except ImportError as e:
    VIBELINT_AVAILABLE = False
    VIBELINT_IMPORT_ERROR = str(e)


def report_to_claude(level: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Report structured output to Claude."""
    output = {
        "level": level,
        "message": message,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    if data:
        output.update(data)

    prefix = f"[VIBELINT-SAFE-{level.upper()}]"
    print(f"{prefix} {json.dumps(output)}", file=sys.stderr)


def run_vibelint_safe(operation: str, *args, **kwargs) -> Dict[str, Any]:
    """Run vibelint operations safely using the API (no subprocess needed)."""
    if not VIBELINT_AVAILABLE:
        return {
            'success': False,
            'error': 'not_available',
            'message': f'Vibelint API not available: {VIBELINT_IMPORT_ERROR}',
            'data': {}
        }

    try:
        # Route to appropriate API function based on operation
        if operation == 'check':
            targets = args if args else ['.']
            exclude_ai = kwargs.get('exclude_ai', False)
            rules = kwargs.get('rules', None)
            cwd = kwargs.get('cwd', None)

            # Change to target directory if specified
            original_cwd = None
            if cwd:
                original_cwd = os.getcwd()
                os.chdir(cwd)

            try:
                result = check_files(list(targets), exclude_ai=exclude_ai, rules=rules)
            finally:
                if original_cwd:
                    os.chdir(original_cwd)

        elif operation == 'validate_file':
            if not args:
                raise ValueError("validate_file requires a file path argument")
            file_path = args[0]
            result = validate_single_file(file_path)

        elif operation == 'justification':
            target_dir = args[0] if args else None
            result = run_project_justification(target_dir)

        else:
            return {
                'success': False,
                'error': 'unknown_operation',
                'message': f'Unknown operation: {operation}',
                'data': {}
            }

        # Convert VibelintResult to compatible format
        return {
            'success': result.success,
            'returncode': 0 if result.success else 1,
            'stdout': result.to_json() if result.success else '',
            'stderr': '\n'.join(result.errors) if result.errors else '',
            'data': result.data,
            'errors': result.errors
        }

    except Exception as e:
        return {
            'success': False,
            'error': 'unexpected',
            'message': str(e),
            'traceback': traceback.format_exc(),
            'data': {}
        }


def run_vibelint_check(target_path: str = ".", format_type: str = "json", timeout: int = 30, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run vibelint check command safely."""
    return run_vibelint_safe('check', target_path, cwd=cwd)


def run_vibelint_validator(validator_module: str, file_path: str, timeout: int = 30) -> Dict[str, Any]:
    """Run specific vibelint validator safely."""
    if validator_module == "validators.single_file.self_validation":
        # For single file validation, use the validate_file API
        return run_vibelint_safe('validate_file', file_path)
    else:
        # For other validators, fall back to check
        return run_vibelint_safe('check', file_path)


def check_validation_failed(result: Dict[str, Any]) -> bool:
    """Check if vibelint found validation issues (not tool failures)."""
    if not result['success']:
        return False  # Tool failure, not validation failure

    if result['returncode'] != 0:
        return True  # Non-zero exit means validation issues

    # Check stderr for vibelint-safe status messages
    if result.get('stderr'):
        if "VIBELINT-SAFE-WARN" in result['stderr']:
            return True

    # Check stdout for validation failure indicators
    if result.get('stdout'):
        failure_patterns = [
            "validation failed",
            "violations found",
            "errors detected",
            "Self-validation failed",
        ]
        return any(pattern in result['stdout'].lower() for pattern in failure_patterns)

    return False


def format_output_safe(result: Dict[str, Any], original_args: List[str]) -> None:
    """Format and output results safely without exiting."""
    if result['success']:
        if result['returncode'] == 0:
            # Success case - output normally
            if result['stdout']:
                print(result['stdout'])
            if result['stderr']:
                print(result['stderr'], file=sys.stderr)
            report_to_claude("INFO", f"Vibelint completed successfully: {' '.join(original_args)}")
        else:
            # Vibelint found issues but ran successfully - this is important for hooks!
            if result['stdout']:
                print(result['stdout'])
            if result['stderr']:
                print(result['stderr'], file=sys.stderr)
            report_to_claude("WARN", f"Vibelint found issues in: {' '.join(original_args)}", {
                'returncode': result['returncode'],
                'original_would_have_failed': True  # This is key information for hooks
            })
    else:
        # Error case - report but don't fail
        report_to_claude("ERROR", f"Vibelint execution failed: {result['message']}", {
            'error_type': result['error'],
            'command': result['command'],
            'original_would_have_failed': False  # Tool error, not validation failure
        })

        # Still output what we can
        if 'stdout' in result and result['stdout']:
            print(result['stdout'])
        if 'stderr' in result and result['stderr']:
            print(result['stderr'], file=sys.stderr)


def main():
    """Main vibelint safe wrapper for CLI usage."""
    try:
        # Get arguments (excluding script name)
        args = sys.argv[1:]

        if not args:
            args = ['--help']

        # Special handling for help
        if '--help' in args or '-h' in args:
            print("Vibelint Safe Mode Wrapper")
            print("Usage: python -m kaia_guardrails.vibelint_safe [operation] [args...]")
            print("")
            print("This wrapper ensures vibelint never causes API breakage with Claude Code.")
            print("Uses vibelint API directly for clean integration.")
            print("")
            print("Operations:")
            print("  check [path]              - Run vibelint checks")
            print("  validate_file <file>      - Validate single file")
            print("  justification [dir]       - Run justification analysis")
            print("")
            print("Examples:")
            print("  python -m kaia_guardrails.vibelint_safe check src/")
            print("  python -m kaia_guardrails.vibelint_safe validate_file file.py")
            print("  python -m kaia_guardrails.vibelint_safe justification .")
            return

        # Parse operation and arguments
        operation = args[0] if args else 'check'
        operation_args = args[1:] if len(args) > 1 else []

        report_to_claude("INFO", f"Running vibelint safely: {operation} {' '.join(operation_args)}")

        # Run vibelint with protection
        result = run_vibelint_safe(operation, *operation_args)

        # Format and output results
        format_output_safe(result, args)

        report_to_claude("INFO", "Vibelint safe execution completed")

    except Exception as e:
        report_to_claude("ERROR", f"Critical error in vibelint safe wrapper: {str(e)}", {
            'traceback': traceback.format_exc()
        })
        print(f"Critical error in vibelint safe wrapper: {str(e)}", file=sys.stderr)

    # Always exit 0 to prevent API breakage
    sys.exit(0)


if __name__ == "__main__":
    main()