#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Hook Performance Profiler

Profiles hook execution times to identify CPU bottlenecks.
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from kaia_guardrails.hooks.base import HookBase, HookError

def get_project_root() -> Path:
    """Find the project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

def profile_hook_execution(hook_path: Path, env_vars: Dict[str, str] = None) -> Dict:
    """Profile execution time of a single hook."""
    if not hook_path.exists():
        return {"error": "Hook not found", "execution_time": 0}

    start_time = time.time()

    try:
        # Set up environment
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        # Execute hook
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )

        end_time = time.time()
        execution_time = end_time - start_time

        return {
            "hook": hook_path.name,
            "execution_time": execution_time,
            "return_code": result.returncode,
            "stdout_length": len(result.stdout),
            "stderr_length": len(result.stderr),
            "stdout": result.stdout[:500],  # First 500 chars
            "stderr": result.stderr[:500] if result.stderr else ""
        }

    except subprocess.TimeoutExpired:
        return {
            "hook": hook_path.name,
            "execution_time": 30.0,
            "error": "Timeout after 30 seconds"
        }
    except Exception as e:
        return {
            "hook": hook_path.name,
            "execution_time": time.time() - start_time,
            "error": str(e)
        }

def find_all_hooks() -> List[Path]:
    """Find all hook files in .claude/hooks directory."""
    project_root = get_project_root()
    hooks_dir = project_root / '.claude' / 'hooks'

    if not hooks_dir.exists():
        return []

    # Find all Python files
    hooks = []
    for file_path in hooks_dir.glob('*.py'):
        if file_path.name != 'hook-profiler.py':  # Don't profile ourselves
            hooks.append(file_path)

    return sorted(hooks)

def simulate_tool_call_env() -> Dict[str, str]:
    """Create environment variables that simulate a tool call."""
    return {
        "CLAUDE_TOOL_NAME": "Read",
        "CLAUDE_FILE_PATHS": "/Users/briyamanick/GitHub/killeraiagent/test.py",
        "CLAUDE_USER_PROMPT": "Profile hook performance"
    }

def main():
    """Main profiling entry point."""
    print("🔍 Hook Performance Profiler")
    print("=" * 50)

    hooks = find_all_hooks()
    if not hooks:
        print("No hooks found to profile")
        return

    env_vars = simulate_tool_call_env()
    total_time = 0
    results = []

    for hook in hooks:
        print(f"Profiling {hook.name}...")
        result = profile_hook_execution(hook, env_vars)
        results.append(result)

        exec_time = result.get('execution_time', 0)
        total_time += exec_time

        if 'error' in result:
            print(f"  ❌ {exec_time:.3f}s - ERROR: {result['error']}")
        else:
            print(f"  ⏱️  {exec_time:.3f}s - RC: {result.get('return_code', 'N/A')}")

    print("\n" + "=" * 50)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 50)

    # Sort by execution time
    results.sort(key=lambda x: x.get('execution_time', 0), reverse=True)

    for result in results:
        exec_time = result.get('execution_time', 0)
        percentage = (exec_time / total_time * 100) if total_time > 0 else 0

        status = "✅" if not result.get('error') and result.get('return_code') == 0 else "❌"
        print(f"{status} {result['hook']:<30} {exec_time:>8.3f}s ({percentage:>5.1f}%)")

        if result.get('error'):
            print(f"    ERROR: {result['error']}")
        elif result.get('stderr'):
            print(f"    STDERR: {result['stderr'][:100]}...")

    print(f"\n🕒 Total hook execution time: {total_time:.3f}s")

    # Save detailed results
    log_file = get_project_root() / '.claude' / 'hook-performance.json'
    with open(log_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_execution_time": total_time,
            "hook_count": len(hooks),
            "results": results
        }, f, indent=2)

    print(f"📄 Detailed results saved to: {log_file}")

    # Performance recommendations
    if total_time > 2.0:
        print(f"\n⚠️  WARNING: Total hook time ({total_time:.3f}s) is high")
        print("   Consider optimizing or disabling slow hooks")

    slowest = results[0] if results else None
    if slowest and slowest.get('execution_time', 0) > 1.0:
        print(f"\n🐌 SLOWEST HOOK: {slowest['hook']} ({slowest.get('execution_time', 0):.3f}s)")
        print("   This hook is a performance bottleneck")

class HookProfilerHook(HookBase):
    """Hook that profiles performance of all hooks."""

    def __init__(self):
        super().__init__(name="hook_profiler", priority=200)  # Run last

    def run(self, context: Dict[str, Any]) -> Any:
        """Run hook performance profiling."""
        # Only run occasionally to avoid overhead
        if context.get('hook_type') != 'PostToolUse':
            return None

        try:
            hooks = find_all_hooks()
            if not hooks:
                return "No hooks found to profile"

            env_vars = simulate_tool_call_env()
            results = []
            total_time = 0

            for hook in hooks[:3]:  # Limit to first 3 hooks to avoid overhead
                result = profile_hook_execution(hook, env_vars)
                results.append(result)
                total_time += result.get('execution_time', 0)

            # Save performance data
            save_performance_data(results)

            slowest = max(results, key=lambda x: x.get('execution_time', 0)) if results else None
            if slowest and slowest.get('execution_time', 0) > 1.0:
                return f"⚠️ Slow hook detected: {slowest.get('hook', 'unknown')} ({slowest.get('execution_time', 0):.3f}s)"

            return f"✅ Profiled {len(results)} hooks, total: {total_time:.3f}s"

        except Exception as e:
            return f"Error profiling hooks: {e}"

if __name__ == '__main__':
    main()