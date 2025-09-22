#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Vibelint single file validation hook.

Uses vibelint-safe to prevent API breakage, but maintains blocking behavior
for quality guardrails by checking if the original vibelint would have failed.
"""
import sys
import subprocess
from pathlib import Path

def main():
    progress_dir = Path(__file__).parent.parent / '.vibelint-progress'
    progress_dir.mkdir(exist_ok=True)
    tracker_file = progress_dir / 'current-failing-file.txt'

    # GUARDRAIL: If called without file path, check if there's a failing file (BLOCKING)
    if len(sys.argv) < 2:
        try:
            if tracker_file.exists():
                with open(tracker_file) as f:
                    failing_file = f.read().strip()
                if failing_file:
                    print(f"🚫 BLOCKED: You must fix failing file first: {failing_file}", file=sys.stderr)
                    sys.exit(1)  # INTENTIONALLY BLOCKING - this is a guardrail
        except Exception as e:
            print(f"[VIBELINT-HOOK-ERROR] Failed to check tracker file: {e}", file=sys.stderr)
        # No failing file tracked, allow operation
        sys.exit(0)

    file_path = Path(sys.argv[1]).resolve()
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(0)  # Don't block unrelated operations

    # GUARDRAIL: If tracker exists, only allow edits to the failing file (BLOCKING)
    try:
        if tracker_file.exists():
            with open(tracker_file) as f:
                failing_file = f.read().strip()
            if failing_file and str(file_path) != failing_file:
                print(f"🚫 BLOCKED: You must fix failing file first: {failing_file}", file=sys.stderr)
                sys.exit(1)  # INTENTIONALLY BLOCKING - this is a guardrail
    except Exception as e:
        print(f"[VIBELINT-HOOK-ERROR] Failed to check failing file tracker: {e}", file=sys.stderr)

    # Run vibelint using safe wrapper (prevents API breakage)
    safe_wrapper = Path(__file__).parent.parent / 'vibelint-safe'
    
    try:
        result = subprocess.run([
            str(safe_wrapper), 'validators.single_file.self_validation', str(file_path)
        ], capture_output=True, text=True, timeout=30)
        
        # vibelint-safe always exits 0, so we need to parse its output to determine
        # if the original vibelint would have failed (for guardrail blocking)
        
        validation_failed = False
        tool_execution_failed = False
        
        # Check stderr for vibelint-safe status messages
        if result.stderr:
            if 'VIBELINT-SAFE-ERROR' in result.stderr:
                # Tool execution failed (module not found, timeout, etc) - don't block
                tool_execution_failed = True
                print(f"[VIBELINT-HOOK-WARN] Vibelint tool failed, allowing operation", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
            elif 'VIBELINT-SAFE-WARN' in result.stderr:
                # Vibelint found actual validation issues - this should block (GUARDRAIL)
                validation_failed = True
        
        # Also check stdout for validation failure indicators
        if result.stdout:
            # Look for common vibelint failure patterns in stdout
            failure_patterns = [
                'validation failed',
                'violations found',
                'errors detected',
                'Self-validation failed'  # This is the actual pattern from vibelint
            ]
            
            if any(pattern in result.stdout.lower() for pattern in failure_patterns):
                validation_failed = True
                
        # Check return code approach: if vibelint-safe captured a non-zero exit,
        # it would be reported in the JSON output
        if 'returncode' in result.stderr and '"returncode": 1' in result.stderr:
            validation_failed = True
        
        if tool_execution_failed:
            # Tool failed to execute - don't block, just warn
            sys.exit(0)
        elif validation_failed:
            # Vibelint found actual code issues - block (GUARDRAIL)
            print(f"🚫 VIBELINT VALIDATION FAILED for {file_path}", file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            # Track the failing file
            try:
                with open(tracker_file, 'w') as f:
                    f.write(str(file_path))
                print(f"[VIBELINT-HOOK-INFO] Tracked failing file: {file_path}", file=sys.stderr)
            except Exception as e:
                print(f"[VIBELINT-HOOK-ERROR] Failed to track failing file: {e}", file=sys.stderr)
            
            sys.exit(1)  # INTENTIONALLY BLOCKING - code quality guardrail
        else:
            # Validation passed
            print(f"[VIBELINT-HOOK-INFO] Validation passed for {file_path}", file=sys.stderr)
            if result.stdout:
                print(result.stdout)
            
            # Clear tracker if validation passed
            try:
                if tracker_file.exists():
                    tracker_file.unlink()
                    print(f"[VIBELINT-HOOK-INFO] Cleared failing file tracker", file=sys.stderr)
            except Exception as e:
                print(f"[VIBELINT-HOOK-ERROR] Failed to clear tracker: {e}", file=sys.stderr)
            
            sys.exit(0)  # Allow operation
        
    except subprocess.TimeoutExpired:
        print(f"[VIBELINT-HOOK-ERROR] Vibelint safe wrapper timed out, allowing operation", file=sys.stderr)
        sys.exit(0)  # Don't block on timeouts
    except Exception as e:
        print(f"[VIBELINT-HOOK-ERROR] Unexpected error: {e}, allowing operation", file=sys.stderr)
        sys.exit(0)  # Don't block on unexpected errors

if __name__ == "__main__":
    main()
