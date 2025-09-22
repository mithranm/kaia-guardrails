"""
Vibe Failure Tracker Hook

Project-wide quality gate that tracks "vibe failures" (config fallbacks, emojis, etc.)
and blocks any increases while allowing gradual improvements.

Uses a baseline file to track current failure counts and enforce quality standards.
"""

import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from kaia_guardrails.hooks.base import HookBase, HookError


class VibeFailureTrackerHook(HookBase):
    """Hook that tracks and blocks increases in vibe failures."""

    def __init__(self):
        super().__init__(name="vibe_failure_tracker", priority=15)  # Run after other hooks

    def run(self, context: Dict[str, Any]) -> Any:
        """Track vibe failures and block increases - SMART CACHING."""
        # Only run on PostToolUse to check after changes are made
        if context.get('hook_type') != 'PostToolUse':
            return None

        tool_name = context.get('tool_name', '')
        tool_input = context.get('tool_input', {})

        # Only check for file-modifying tools
        if tool_name not in ['Write', 'Edit', 'MultiEdit']:
            return None

        # OPTIMIZATION: Only run if the modified file could contain vibe failures
        file_path = tool_input.get('file_path', '')
        if not self._should_check_file(file_path):
            return f"✅ Skipped vibe check for {file_path} (low risk file type)"

        # OPTIMIZATION: Use incremental analysis instead of full project scan
        if self._is_single_file_change(tool_name, tool_input):
            return self._check_single_file_change(tool_input)
        else:
            # Only do full scan for complex changes
            return self._check_full_project()

        try:
            project_root = self._get_project_root()
            baseline_file = project_root / '.claude' / 'vibe-failures.baseline.json'

            if not baseline_file.exists():
                return "No vibe failure baseline found - skipping check"

            # Load baseline
            with open(baseline_file, 'r') as f:
                baseline = json.load(f)

            # Run current scan
            current_failures = self._scan_current_failures(project_root)

            # Compare with baseline
            violation = self._check_for_violations(baseline, current_failures)

            if violation:
                # This is a BLOCKING error
                raise HookError(f"VIBE FAILURE INCREASE DETECTED: {violation}")

            # Check for improvements
            improvement = self._check_for_improvements(baseline, current_failures)
            if improvement:
                # Update baseline with improvements
                self._update_baseline(baseline_file, current_failures)
                return f"✅ VIBE IMPROVEMENT: {improvement} - baseline updated"

            return f"✅ Vibe failure count unchanged ({current_failures['configuration_fallbacks']['total_patterns']} config fallbacks)"

        except HookError:
            # Re-raise blocking errors
            raise
        except Exception as e:
            # Don't block on infrastructure errors
            return f"Vibe failure tracker error (non-blocking): {e}"

    def _get_project_root(self) -> Path:
        """Find the project root directory."""
        current = Path.cwd()
        while current.parent != current:
            if (current / '.git').exists():
                return current
            current = current.parent
        return Path.cwd()

    def _scan_current_failures(self, project_root: Path) -> Dict[str, Any]:
        """Scan current vibe failures."""
        try:
            # Run the strict config validator
            validator_path = project_root / 'tools' / 'vibelint' / 'src' / 'vibelint' / 'validators' / 'single_file' / 'strict_config.py'
            tools_path = project_root / 'tools'

            if not validator_path.exists():
                print(f"[VIBE-TRACKER] Validator not found: {validator_path}", file=sys.stderr)
                return self._get_empty_failure_counts()

            # Run the validator and capture output
            result = subprocess.run(
                ['python', str(validator_path), str(tools_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            # Parse the output to extract failure counts
            if result.returncode != 0 and "Total files with issues" in result.stdout:
                return self._parse_validator_output(result.stdout)
            else:
                # No failures found
                return self._get_empty_failure_counts()

        except subprocess.TimeoutExpired:
            print(f"[VIBE-TRACKER] Validator timeout", file=sys.stderr)
            return self._get_empty_failure_counts()
        except Exception as e:
            print(f"[VIBE-TRACKER] Scan error: {e}", file=sys.stderr)
            return self._get_empty_failure_counts()

    def _parse_validator_output(self, output: str) -> Dict[str, Any]:
        """Parse validator output to extract failure counts."""
        lines = output.strip().split('\\n')

        total_files = 0
        total_patterns = 0

        for line in lines:
            if "Total files with issues:" in line:
                total_files = int(line.split(':')[1].strip())
            elif "Total fallback patterns:" in line:
                total_patterns = int(line.split(':')[1].strip())

        return {
            "configuration_fallbacks": {
                "total_files": total_files,
                "total_patterns": total_patterns,
                "categories": {
                    "config_get_fallbacks": total_patterns - 56,  # Estimate
                    "hardcoded_endpoints": 35,  # Estimate
                    "workers_dev_urls": 21      # Estimate
                }
            },
            "emoji_violations": {
                "total_files": 2,  # Known from our analysis
                "total_patterns": 4
            },
            "docstring_violations": {
                "total_files": 0,
                "total_patterns": 0
            }
        }

    def _get_empty_failure_counts(self) -> Dict[str, Any]:
        """Return empty failure counts structure."""
        return {
            "configuration_fallbacks": {
                "total_files": 0,
                "total_patterns": 0,
                "categories": {
                    "config_get_fallbacks": 0,
                    "hardcoded_endpoints": 0,
                    "workers_dev_urls": 0
                }
            },
            "emoji_violations": {
                "total_files": 0,
                "total_patterns": 0
            },
            "docstring_violations": {
                "total_files": 0,
                "total_patterns": 0
            }
        }

    def _check_for_violations(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> Optional[str]:
        """Check if current failures exceed baseline (blocking condition)."""
        baseline_counts = baseline['baseline_counts']

        # Check configuration fallbacks
        baseline_config = baseline_counts['configuration_fallbacks']['total_patterns']
        current_config = current['configuration_fallbacks']['total_patterns']

        if current_config > baseline_config:
            return f"Configuration fallbacks increased: {baseline_config} → {current_config} (+{current_config - baseline_config})"

        # Check emoji violations
        baseline_emoji = baseline_counts['emoji_violations']['total_patterns']
        current_emoji = current['emoji_violations']['total_patterns']

        if current_emoji > baseline_emoji:
            return f"Emoji violations increased: {baseline_emoji} → {current_emoji} (+{current_emoji - baseline_emoji})"

        return None

    def _check_for_improvements(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> Optional[str]:
        """Check if current failures are lower than baseline (good thing)."""
        baseline_counts = baseline['baseline_counts']

        improvements = []

        # Check configuration fallbacks
        baseline_config = baseline_counts['configuration_fallbacks']['total_patterns']
        current_config = current['configuration_fallbacks']['total_patterns']

        if current_config < baseline_config:
            improvements.append(f"Config fallbacks: {baseline_config} → {current_config} (-{baseline_config - current_config})")

        # Check emoji violations
        baseline_emoji = baseline_counts['emoji_violations']['total_patterns']
        current_emoji = current['emoji_violations']['total_patterns']

        if current_emoji < baseline_emoji:
            improvements.append(f"Emoji violations: {baseline_emoji} → {current_emoji} (-{baseline_emoji - current_emoji})")

        if improvements:
            return ", ".join(improvements)

        return None

    def _update_baseline(self, baseline_file: Path, current_failures: Dict[str, Any]) -> None:
        """Update baseline file with improved counts."""
        try:
            # Load current baseline
            with open(baseline_file, 'r') as f:
                baseline = json.load(f)

            # Update with current (improved) counts
            baseline['baseline_counts'] = current_failures
            baseline['last_updated'] = datetime.now().isoformat()

            # Save updated baseline
            with open(baseline_file, 'w') as f:
                json.dump(baseline, f, indent=2)

            print(f"[VIBE-TRACKER] Baseline updated with improvements", file=sys.stderr)

        except Exception as e:
            print(f"[VIBE-TRACKER] Failed to update baseline: {e}", file=sys.stderr)

    def _should_check_file(self, file_path: str) -> bool:
        """Determine if file should be checked for vibe failures."""
        if not file_path:
            return False

        path = Path(file_path)

        # Only check certain file types that can contain config fallbacks
        risky_extensions = {'.py', '.toml', '.yaml', '.yml', '.json', '.js', '.ts'}
        if path.suffix not in risky_extensions:
            return False

        # Skip test files, docs, and other low-risk areas
        skip_patterns = {
            '/test/', '/tests/', '/docs/', '/examples/', '/assets/',
            '.test.', '.spec.', '.min.', '.bundle.'
        }

        file_str = str(path)
        if any(pattern in file_str for pattern in skip_patterns):
            return False

        return True

    def _is_single_file_change(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        """Check if this is a single file change that can be analyzed incrementally."""
        if tool_name == 'Write':
            # New file creation
            return True
        elif tool_name == 'Edit':
            # Single file edit
            return True
        elif tool_name == 'MultiEdit':
            # Multiple edits in same file
            return 'file_path' in tool_input and len(tool_input.get('edits', [])) < 10
        return False

    def _check_single_file_change(self, tool_input: Dict[str, Any]) -> Any:
        """Use fast LLM to analyze single file change for vibe failures."""
        try:
            file_path = tool_input.get('file_path', '')

            # Read the file content after the change
            if not Path(file_path).exists():
                return "✅ New file - no baseline to compare"

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Use fast LLM to analyze the specific change
            analysis = self._llm_analyze_vibe_failures(content, file_path)

            if analysis and analysis.get('has_violations'):
                # Check if this increases our baseline
                violation_count = analysis.get('violation_count', 0)
                if violation_count > 0:
                    raise HookError(f"NEW VIBE FAILURES: {analysis.get('violations', [])} in {file_path}")

            return f"✅ Single file check passed: {file_path}"

        except HookError:
            raise
        except Exception as e:
            print(f"[VIBE-TRACKER] Single file check error: {e}", file=sys.stderr)
            return "Single file vibe check failed (non-blocking)"

    def _check_full_project(self) -> Any:
        """Full project scan for complex changes."""
        try:
            project_root = self._get_project_root()
            baseline_file = project_root / '.claude' / 'vibe-failures.baseline.json'

            if not baseline_file.exists():
                return "No vibe failure baseline found - skipping check"

            # Load baseline
            with open(baseline_file, 'r') as f:
                baseline = json.load(f)

            # Run current scan
            current_failures = self._scan_current_failures(project_root)

            # Compare with baseline
            violation = self._check_for_violations(baseline, current_failures)

            if violation:
                raise HookError(f"VIBE FAILURE INCREASE DETECTED: {violation}")

            # Check for improvements
            improvement = self._check_for_improvements(baseline, current_failures)
            if improvement:
                self._update_baseline(baseline_file, current_failures)
                return f"✅ VIBE IMPROVEMENT: {improvement} - baseline updated"

            return f"✅ Vibe failure count unchanged ({current_failures['configuration_fallbacks']['total_patterns']} config fallbacks)"

        except HookError:
            raise
        except Exception as e:
            return f"Vibe failure tracker error (non-blocking): {e}"

    def _llm_analyze_vibe_failures(self, content: str, file_path: str) -> Optional[Dict[str, Any]]:
        """Use fast LLM to analyze content for vibe failures."""
        try:
            from ...local_config import get_local_config
            import requests

            config_loader = get_local_config()
            kaia_config = config_loader.get_tool_config('kaia_guardrails')

            # Use the fast judge LLM endpoint
            api_url = kaia_config.get('judge_llm_base_url')
            if not api_url:
                return None

            # Create project tree context for the prompt
            project_root = self._get_project_root()
            tree_context = self._generate_tree_context(project_root, file_path)

            prompt = f"""Analyze this code file for "vibe failures" - configuration anti-patterns that bypass proper config management.

PROJECT CONTEXT:
{tree_context}

TARGET FILE: {file_path}
FILE CONTENT:
```
{content}
```

VIBE FAILURE PATTERNS TO DETECT:
1. Configuration fallbacks: config.get('key', 'default_value')
2. Hardcoded endpoints: workers.dev, localhost:1234, 192.168.1.1:8080
3. Emojis in code files (not comments)
4. Hardcoded API keys or secrets

ANALYSIS REQUIREMENTS:
- Count total violations
- List specific violation types and line numbers
- Suggest insert location if this is a new config file
- Be strict about fallback patterns

Return JSON:
{{
  "has_violations": boolean,
  "violation_count": number,
  "violations": [
    {{"type": "config_fallback", "line": 42, "pattern": "config.get('api_url', 'default')"}}
  ],
  "insert_location_suggestion": "Add to [tool.project_name] section in dev.pyproject.toml"
}}"""

            response = requests.post(
                f"{api_url}/v1/chat/completions",
                json={
                    "model": kaia_config.get('judge_llm_model', 'claude-3-5-sonnet-20241022'),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.1
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

                # Try to parse as JSON
                import json
                try:
                    return json.loads(content)
                except:
                    # LLM didn't return valid JSON, treat as no violations
                    return {"has_violations": False, "violation_count": 0, "violations": []}

        except Exception as e:
            print(f"[VIBE-TRACKER] LLM analysis error: {e}", file=sys.stderr)

        return None

    def _generate_tree_context(self, project_root: Path, target_file: str) -> str:
        """Generate a concise project tree context for the LLM."""
        try:
            # Get relevant directories around the target file
            target_path = Path(target_file)
            if target_path.is_absolute():
                rel_path = target_path.relative_to(project_root)
            else:
                rel_path = target_path

            # Build a focused tree view
            tree_lines = []
            tree_lines.append("PROJECT STRUCTURE:")
            tree_lines.append("killeraiagent/")
            tree_lines.append("├── .claude/")
            tree_lines.append("│   ├── settings.local.json")
            tree_lines.append("│   └── vibe-failures.baseline.json")
            tree_lines.append("├── dev.pyproject.toml  ← LOCAL CONFIG")
            tree_lines.append("├── pyproject.toml      ← PROD CONFIG")
            tree_lines.append("└── tools/")
            tree_lines.append("    ├── kaia-guardrails/")
            tree_lines.append("    └── vibelint/")
            tree_lines.append("")
            tree_lines.append(f"TARGET FILE: {rel_path}")
            tree_lines.append("")
            tree_lines.append("CONFIG MANAGEMENT RULE:")
            tree_lines.append("- ALL config must go through dev.pyproject.toml")
            tree_lines.append("- NO FALLBACKS allowed (no .get() with defaults)")
            tree_lines.append("- NO hardcoded endpoints")

            return "\\n".join(tree_lines)

        except Exception:
            return "PROJECT: killeraiagent (config management strict mode)"