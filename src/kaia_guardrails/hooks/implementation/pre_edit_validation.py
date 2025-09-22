#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Pre-edit validation hook.

Runs validation checks before editing files.
Uses vibelint-safe wrapper to prevent API breakage.
"""

import os
import sys
import subprocess
from pathlib import Path

def run_validator(script_name: str, file_path: str) -> tuple[bool, str]:
    """Run a validator script. Returns (success, output)."""
    script_path = Path(__file__).parent / script_name
    result = subprocess.run(
        [sys.executable, str(script_path), file_path],
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.returncode == 0, result.stdout + result.stderr

def should_check_vibelint(file_path: str) -> bool:
    """Check if file should be validated with vibelint."""
    return file_path.endswith('.py') and 'vibelint' in file_path

def main():
    """Run pre-edit validation checks."""
    if len(sys.argv) < 2:
        print("Usage: pre-edit-validation.py <file_path>", file=sys.stderr)
        sys.exit(1)
    
    file_path = sys.argv[1]
    fp = Path(file_path).resolve()
    
    if not fp.exists():
        print(f"File not found: {fp}", file=sys.stderr)
        sys.exit(0)  # Don't block if file doesn't exist
    
    print(f"[PRE-EDIT] Validating {fp}", file=sys.stderr)
    
    validation_failed = False
    failure_messages = []
    
    # Run file-specific validators
    validators = [
        'emoji-check.py',
        'detect-nested-claude-dirs.py'
    ]
    
    for validator in validators:
        validator_path = Path(__file__).parent / validator
        if validator_path.exists():
            success, output = run_validator(validator, str(fp))
            if not success:
                validation_failed = True
                failure_messages.append(f"{validator}: {output}")
    
    # Run vibelint self-validation if needed (using safe wrapper)
    if should_check_vibelint(str(fp)):
        safe_wrapper = Path(__file__).parent.parent / 'vibelint-safe'
        result = subprocess.run([
            str(safe_wrapper), 'validators.single_file.self_validation', str(fp)
        ], capture_output=True, text=True)
        
        # Check if validation found issues by looking at stderr
        if result.stderr and ('VIBELINT-SAFE-WARN' in result.stderr or 'VIBELINT-SAFE-ERROR' in result.stderr):
            validation_failed = True
            failure_messages.append(f"vibelint: {result.stderr}")
    
    if validation_failed:
        print("[PRE-EDIT] Validation failed:", file=sys.stderr)
        for msg in failure_messages:
            print(f"  - {msg}", file=sys.stderr)
        print("[PRE-EDIT] Please fix issues before editing", file=sys.stderr)
        sys.exit(1)
    else:
        print("[PRE-EDIT] Validation passed", file=sys.stderr)
        sys.exit(0)

if __name__ == '__main__':
    main()
