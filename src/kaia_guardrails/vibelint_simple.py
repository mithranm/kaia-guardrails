"""
Simple vibelint wrapper that uses subprocess but with clean error handling.

This is a pragmatic approach that uses subprocess but makes it reliable and
predictable for integration with kaia-guardrails hooks.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_vibelint_command(args: List[str], cwd: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Run vibelint command with reliable error handling.

    Args:
        args: Command arguments (e.g., ['check', '.', '--format', 'json'])
        cwd: Working directory for command execution
        timeout: Command timeout in seconds

    Returns:
        Dict with success, output, and error information
    """
    try:
        # Build command
        cmd = [sys.executable, '-m', 'vibelint'] + args

        # Set up environment
        env = os.environ.copy()
        vibelint_path = "/Users/briyamanick/GitHub/killeraiagent/tools/vibelint/src"

        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{vibelint_path}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = vibelint_path

        # Run command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env
        )

        return {
            'success': True,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'command': ' '.join(cmd)
        }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'timeout',
            'message': f'Command timed out after {timeout} seconds',
            'returncode': -1
        }

    except FileNotFoundError:
        return {
            'success': False,
            'error': 'not_found',
            'message': 'vibelint module not found - check installation',
            'returncode': -1
        }

    except Exception as e:
        return {
            'success': False,
            'error': 'unexpected',
            'message': str(e),
            'returncode': -1
        }


def check_files(targets: Optional[List[str]] = None, cwd: Optional[str] = None,
                exclude_ai: bool = False, timeout: int = 60) -> Dict[str, Any]:
    """Run vibelint check on files/directories."""
    args = ['check']
    if targets:
        args.extend(targets)
    else:
        args.append('.')

    args.extend(['--format', 'json'])

    if exclude_ai:
        args.append('--exclude-ai')

    return run_vibelint_command(args, cwd, timeout)


def validate_single_file(file_path: str, cwd: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """Run vibelint validation on a single file."""
    return check_files([file_path], cwd, timeout=timeout)


def has_validation_issues(result: Dict[str, Any]) -> bool:
    """Check if vibelint found actual validation issues (not tool errors)."""
    if not result.get('success', False):
        return False  # Tool failed, not validation failure

    # Non-zero exit code indicates validation issues
    if result.get('returncode', 0) != 0:
        return True

    # Parse JSON output to check for issues
    stdout = result.get('stdout', '')
    if stdout:
        try:
            data = json.loads(stdout)
            summary = data.get('summary', {})
            total_issues = sum(summary.values()) if summary else 0
            return total_issues > 0
        except json.JSONDecodeError:
            # If not JSON, check for error patterns
            return any(pattern in stdout.lower() for pattern in [
                'error', 'failed', 'violation', 'block'
            ])

    return False


def format_vibelint_output(result: Dict[str, Any]) -> str:
    """Format vibelint output for display."""
    if not result.get('success', False):
        return f"❌ Vibelint execution failed: {result.get('message', 'Unknown error')}"

    if result.get('returncode', 0) == 0:
        stdout = result.get('stdout', '')
        if stdout:
            try:
                data = json.loads(stdout)
                summary = data.get('summary', {})
                total_issues = sum(summary.values()) if summary else 0
                if total_issues > 0:
                    return f"📊 Vibelint found {total_issues} issues: {summary}"
                else:
                    return "✨ No vibelint issues found"
            except json.JSONDecodeError:
                return "📊 Vibelint analysis completed"
        else:
            return "✨ No vibelint issues found"
    else:
        return f"⚠️ Vibelint found issues (exit code: {result.get('returncode')})"