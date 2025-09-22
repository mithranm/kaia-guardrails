"""
Focus Process Management System

Implements stack-based focus process tracking with git branching support.
Prevents circular dependencies and provides escape hatches.
"""
import os
import json
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class FocusProcessManager:
    """Manages focus process stack with git integration and circular dependency detection."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or self._get_project_root()
        self.claude_dir = self.project_root / '.claude'
        self.stack_file = self.claude_dir / 'focus-process-stack.json'
        self.current_process_file = self.claude_dir / 'current-process.txt'

    def _get_project_root(self) -> Path:
        """Find the project root directory."""
        current = Path.cwd()
        while current.parent != current:
            if (current / '.git').exists():
                return current
            current = current.parent
        return Path.cwd()

    def load_focus_stack(self) -> Dict[str, Any]:
        """Load the current focus process stack."""
        if not self.stack_file.exists():
            return self._create_empty_stack()

        try:
            with open(self.stack_file) as f:
                return json.load(f)
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to load stack: {e}")
            return self._create_empty_stack()

    def _create_empty_stack(self) -> Dict[str, Any]:
        """Create an empty focus process stack."""
        return {
            "current_focus": None,
            "description": "",
            "last_updated": datetime.now().isoformat(),
            "focus_process_stack": [],
            "circular_dependency_tracker": {
                "detected": False,
                "dependency_chain": [],
                "escape_hatch_triggered": False
            },
            "branching_strategy": {
                "create_branch_per_focus": True,
                "commit_after_every_edit": True,
                "allow_focus_fork": True,
                "prevent_circular_branching": True
            }
        }

    def save_focus_stack(self, stack_data: Dict[str, Any]) -> bool:
        """Save the focus process stack."""
        try:
            stack_data["last_updated"] = datetime.now().isoformat()
            with open(self.stack_file, 'w') as f:
                json.dump(stack_data, f, indent=2)
            return True
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to save stack: {e}")
            return False

    def push_focus_process(self, focus_id: str, description: str,
                          create_branch: bool = True, auto_commit: bool = True) -> bool:
        """Push a new focus process onto the stack."""
        stack = self.load_focus_stack()

        # Check for circular dependencies
        if self._detect_circular_dependency(stack, focus_id):
            print(f"[FOCUS-MANAGER-ERROR] Circular dependency detected for focus: {focus_id}")
            stack["circular_dependency_tracker"]["detected"] = True
            stack["circular_dependency_tracker"]["dependency_chain"].append(focus_id)
            self.save_focus_stack(stack)
            return False

        # Get current git commit for rollback
        git_commit = self._get_current_git_commit() if create_branch else None

        # Create git branch if requested
        branch_name = None
        if create_branch:
            branch_name = f"focus/{focus_id.replace('_', '-')}"
            if not self._create_git_branch(branch_name):
                print(f"[FOCUS-MANAGER-ERROR] Failed to create branch: {branch_name}")
                return False

        # Create new focus process entry
        new_focus = {
            "focus_id": focus_id,
            "description": description,
            "branch_name": branch_name,
            "started_at": datetime.now().isoformat(),
            "parent_focus": stack.get("current_focus"),
            "git_commit_before": git_commit,
            "escape_hatch_available": True,
            "requires_git_branching": create_branch,
            "auto_commit_on_edit": auto_commit
        }

        # Update stack
        stack["focus_process_stack"].append(new_focus)
        stack["current_focus"] = focus_id
        stack["description"] = description

        # Update current process file
        try:
            with open(self.current_process_file, 'w') as f:
                f.write(description)
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to update current process file: {e}")

        return self.save_focus_stack(stack)

    def pop_focus_process(self, force_escape: bool = False, merge_strategy: str = "auto") -> bool:
        """
        Pop the current focus process from the stack.

        Args:
            force_escape: If True, skip merge and force removal (used for escape hatch)
            merge_strategy: "auto", "squash", "merge", or "no-merge"
        """
        stack = self.load_focus_stack()

        if not stack["focus_process_stack"]:
            print("[FOCUS-MANAGER-WARN] No focus process to pop")
            return False

        current_focus = stack["focus_process_stack"].pop()
        focus_branch = current_focus.get("branch_name")

        if not force_escape and focus_branch:
            # Successful completion - perform merge
            success = self._complete_focus_with_merge(current_focus, merge_strategy)
            if not success:
                print(f"[FOCUS-MANAGER-ERROR] Failed to merge focus: {current_focus['focus_id']}")
                # Re-add to stack if merge failed
                stack["focus_process_stack"].append(current_focus)
                return False

        # Restore parent focus
        if stack["focus_process_stack"]:
            parent_focus = stack["focus_process_stack"][-1]
            stack["current_focus"] = parent_focus["focus_id"]
            stack["description"] = parent_focus["description"]

            # Switch back to parent branch
            if parent_focus.get("branch_name") and not force_escape:
                self._switch_git_branch(parent_focus["branch_name"])
        else:
            stack["current_focus"] = None
            stack["description"] = ""

            # Switch to main branch if no focus processes remain
            if not force_escape:
                self._switch_git_branch("main")

        # Periodic push to remote if configured
        self._periodic_remote_push()

        # Update current process file
        try:
            with open(self.current_process_file, 'w') as f:
                f.write(stack["description"])
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to update current process file: {e}")

        return self.save_focus_stack(stack)

    def _complete_focus_with_merge(self, focus: Dict[str, Any], merge_strategy: str) -> bool:
        """
        Complete a focus process by merging its branch into the parent.

        Args:
            focus: The focus process to complete
            merge_strategy: How to merge the focus branch
        """
        try:
            focus_branch = focus.get("branch_name")
            if not focus_branch:
                print("[FOCUS-MANAGER] No branch to merge, focus completed without git operations")
                return True

            # Determine target branch
            stack = self.load_focus_stack()
            if len(stack["focus_process_stack"]) > 1:
                # Merge into parent focus branch
                parent_focus = stack["focus_process_stack"][-2]
                target_branch = parent_focus.get("branch_name", "main")
            else:
                # Merge into main branch
                target_branch = "main"

            print(f"[FOCUS-MANAGER] Completing focus: {focus['focus_id']}")
            print(f"[FOCUS-MANAGER] Merging {focus_branch} -> {target_branch}")

            # Commit any pending changes
            if focus.get("auto_commit_on_edit"):
                self._auto_commit_changes("Final commit before focus completion")

            # Switch to target branch
            if not self._switch_git_branch(target_branch):
                print(f"[FOCUS-MANAGER-ERROR] Failed to switch to target branch: {target_branch}")
                return False

            # Perform merge based on strategy
            if merge_strategy == "squash":
                success = self._squash_merge_branch(focus_branch, focus)
            elif merge_strategy == "merge":
                success = self._merge_branch(focus_branch, focus)
            elif merge_strategy == "no-merge":
                print(f"[FOCUS-MANAGER] Skipping merge as requested")
                success = True
            else:  # auto strategy
                # Use squash for small focuses, merge for complex ones
                commit_count = len(focus.get("commit_history", []))
                if commit_count <= 3:
                    success = self._squash_merge_branch(focus_branch, focus)
                else:
                    success = self._merge_branch(focus_branch, focus)

            if success:
                # Delete the focus branch after successful merge
                self._delete_merged_branch(focus_branch)
                print(f"[FOCUS-MANAGER] Successfully completed focus: {focus['focus_id']}")

            return success

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Focus completion failed: {e}")
            return False

    def _squash_merge_branch(self, source_branch: str, focus: Dict[str, Any]) -> bool:
        """Perform a squash merge of the focus branch."""
        try:
            # Create comprehensive squash commit message
            commit_msg = self._create_squash_commit_message(focus)

            # Squash merge
            result = subprocess.run([
                "git", "merge", "--squash", source_branch
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[FOCUS-MANAGER-ERROR] Squash merge failed: {result.stderr}")
                return False

            # Commit the squashed changes
            result = subprocess.run([
                "git", "commit", "-m", commit_msg
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[FOCUS-MANAGER-ERROR] Squash commit failed: {result.stderr}")
                return False

            print(f"[FOCUS-MANAGER] Squash merged {source_branch}")
            return True

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Squash merge error: {e}")
            return False

    def _merge_branch(self, source_branch: str, focus: Dict[str, Any]) -> bool:
        """Perform a regular merge of the focus branch."""
        try:
            # Create merge commit message
            commit_msg = f"Merge focus process: {focus['focus_id']}\n\n{focus.get('description', '')}\n\nFocus-Process-Completion: {focus['focus_id']}\nCommits-Merged: {len(focus.get('commit_history', []))}\nBranch-Merged: {source_branch}"

            # Regular merge
            result = subprocess.run([
                "git", "merge", "--no-ff", "-m", commit_msg, source_branch
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[FOCUS-MANAGER-ERROR] Merge failed: {result.stderr}")
                return False

            print(f"[FOCUS-MANAGER] Merged {source_branch} with merge commit")
            return True

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Merge error: {e}")
            return False

    def _create_squash_commit_message(self, focus: Dict[str, Any]) -> str:
        """Create a comprehensive commit message for squash merges."""
        focus_id = focus['focus_id']
        description = focus.get('description', 'No description')
        commit_history = focus.get('commit_history', [])

        # Primary message
        msg = f"Complete focus process: {focus_id}\n\n{description}\n\n"

        # Add commit summary
        if commit_history:
            msg += f"Squashed {len(commit_history)} commits:\n"
            for i, commit in enumerate(commit_history, 1):
                tool_name = commit.get('tool_name', 'unknown')
                timestamp = commit.get('timestamp', '')[:19]  # Remove microseconds
                files = commit.get('file_paths', [])
                file_names = [Path(f).name for f in files[:2]]  # First 2 files
                msg += f"  {i}. {tool_name} - {', '.join(file_names)} ({timestamp})\n"

        # Add metadata
        msg += f"\nFocus-Process-Completion: {focus_id}\n"
        msg += f"Focus-Branch: {focus.get('branch_name', 'unknown')}\n"
        msg += f"Commits-Squashed: {len(commit_history)}\n"
        msg += f"Completion-Strategy: squash-merge\n"
        msg += f"Completed-At: {datetime.now().isoformat()}\n"

        return msg

    def _delete_merged_branch(self, branch_name: str) -> bool:
        """Delete a branch after successful merge."""
        try:
            result = subprocess.run([
                "git", "branch", "-d", branch_name
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"[FOCUS-MANAGER] Deleted merged branch: {branch_name}")
                return True
            else:
                print(f"[FOCUS-MANAGER-WARN] Failed to delete branch {branch_name}: {result.stderr}")
                return False

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Branch deletion error: {e}")
            return False

    def _periodic_remote_push(self) -> bool:
        """
        Periodically push to remote repository for backup and collaboration.
        """
        try:
            # Check if we should push (configurable interval)
            if not self._should_push_to_remote():
                return True

            # Get current branch
            current_branch = self._get_current_branch()
            if not current_branch:
                return False

            print(f"[FOCUS-MANAGER] Pushing {current_branch} to remote...")

            # Push current branch to remote
            result = subprocess.run([
                "git", "push", "origin", current_branch
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"[FOCUS-MANAGER] Successfully pushed {current_branch} to remote")
                self._update_last_push_time()
                return True
            else:
                print(f"[FOCUS-MANAGER-WARN] Push failed: {result.stderr}")
                # Don't fail the operation if push fails
                return True

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Remote push error: {e}")
            return True  # Don't fail the main operation

    def _should_push_to_remote(self) -> bool:
        """Determine if we should push to remote based on configuration and timing."""
        try:
            # Load configuration
            config = self._load_push_config()

            if not config.get("auto_push_enabled", False):
                return False

            # Check time-based pushing
            push_interval = config.get("push_interval_minutes", 30)
            last_push_time = config.get("last_push_time")

            if not last_push_time:
                return True  # First push

            from datetime import datetime, timedelta
            last_push = datetime.fromisoformat(last_push_time)
            time_since_push = datetime.now() - last_push

            if time_since_push > timedelta(minutes=push_interval):
                return True

            # Check commit-based pushing
            commits_since_push = self._count_commits_since_push()
            max_commits = config.get("max_commits_before_push", 10)

            if commits_since_push >= max_commits:
                return True

            return False

        except Exception:
            return False  # Default to not pushing on error

    def _load_push_config(self) -> Dict[str, Any]:
        """Load push configuration from claude directory."""
        try:
            config_file = self.claude_dir / "push_config.json"
            if config_file.exists():
                with open(config_file) as f:
                    return json.load(f)
            else:
                # Create default config
                default_config = {
                    "auto_push_enabled": True,
                    "push_interval_minutes": 30,
                    "max_commits_before_push": 10,
                    "last_push_time": None,
                    "last_push_commit": None
                }
                with open(config_file, 'w') as f:
                    json.dump(default_config, f, indent=2)
                return default_config
        except Exception:
            return {"auto_push_enabled": False}

    def _update_last_push_time(self):
        """Update the last push timestamp in configuration."""
        try:
            config = self._load_push_config()
            config["last_push_time"] = datetime.now().isoformat()
            config["last_push_commit"] = self._get_current_git_commit()

            config_file = self.claude_dir / "push_config.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to update push time: {e}")

    def _count_commits_since_push(self) -> int:
        """Count commits since last push."""
        try:
            config = self._load_push_config()
            last_push_commit = config.get("last_push_commit")

            if not last_push_commit:
                return 100  # Force push if no previous push recorded

            # Count commits between last push and HEAD
            result = subprocess.run([
                "git", "rev-list", "--count", f"{last_push_commit}..HEAD"
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                return int(result.stdout.strip())
            else:
                return 0

        except Exception:
            return 0

    def _get_current_branch(self) -> Optional[str]:
        """Get the current git branch name."""
        try:
            result = subprocess.run([
                "git", "branch", "--show-current"
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None

        except Exception:
            return None

    def trigger_escape_hatch(self, reason: str, escape_levels: int = 1,
                            use_vibelint_judge: bool = True) -> bool:
        """
        Trigger escape hatch to exit focus processes with intelligent traversal.

        Args:
            reason: Why the escape is being triggered
            escape_levels: Number of stack levels to escape (0 = escape all, 1 = current only)
            use_vibelint_judge: Whether to use vibelint LLMs to determine optimal escape level
        """
        stack = self.load_focus_stack()

        if not stack["focus_process_stack"]:
            print("[FOCUS-MANAGER-WARN] No focus process to escape from")
            return False

        # Determine optimal escape level using vibelint if requested
        if use_vibelint_judge and escape_levels == 1:
            escape_levels = self._get_vibelint_escape_recommendation(stack, reason)

        # Validate escape levels
        max_levels = len(stack["focus_process_stack"])
        if escape_levels <= 0:
            escape_levels = max_levels  # Escape all levels
        else:
            escape_levels = min(escape_levels, max_levels)

        print(f"[FOCUS-MANAGER] Escape hatch triggered: {reason}")
        print(f"[FOCUS-MANAGER] Escaping {escape_levels} level(s) from stack of {max_levels}")

        # Mark escape hatch as triggered
        stack["circular_dependency_tracker"]["escape_hatch_triggered"] = True
        stack["circular_dependency_tracker"]["escape_reason"] = reason
        stack["circular_dependency_tracker"]["escape_levels"] = escape_levels

        # Store current git state before escape
        current_commit = self._get_current_git_commit()
        stack["circular_dependency_tracker"]["pre_escape_commit"] = current_commit

        # Escape the specified number of levels
        escaped_focuses = []
        for level in range(escape_levels):
            if not stack["focus_process_stack"]:
                break

            focus_to_escape = stack["focus_process_stack"][-1]
            escaped_focuses.append(focus_to_escape)

            print(f"[FOCUS-MANAGER] Escaping level {level + 1}: {focus_to_escape['focus_id']}")

            # Revert git state for this focus if available
            if focus_to_escape.get("git_commit_before"):
                print(f"[FOCUS-MANAGER] Reverting to commit: {focus_to_escape['git_commit_before'][:8]}")
                self._revert_to_git_commit(focus_to_escape["git_commit_before"])

            # Remove from stack
            stack["focus_process_stack"].pop()

        # Update current focus to the new top of stack (or None if empty)
        if stack["focus_process_stack"]:
            new_current = stack["focus_process_stack"][-1]
            stack["current_focus"] = new_current["focus_id"]
            stack["description"] = new_current["description"]

            # Switch to the branch of the new current focus
            if new_current.get("branch_name"):
                self._switch_git_branch(new_current["branch_name"])

            print(f"[FOCUS-MANAGER] Returned to focus: {new_current['focus_id']}")
        else:
            stack["current_focus"] = None
            stack["description"] = ""

            # Switch to main branch if no focus processes remain
            self._switch_git_branch("main")
            print("[FOCUS-MANAGER] Returned to main branch - no active focus processes")

        # Save escape information for analysis
        stack["last_escape"] = {
            "reason": reason,
            "escaped_focuses": [f["focus_id"] for f in escaped_focuses],
            "escape_levels": escape_levels,
            "timestamp": datetime.now().isoformat(),
            "pre_escape_commit": current_commit
        }

        # Update current process file
        try:
            with open(self.current_process_file, 'w') as f:
                f.write(stack["description"])
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to update current process file: {e}")

        return self.save_focus_stack(stack)

    def _get_vibelint_escape_recommendation(self, stack: Dict[str, Any], reason: str) -> int:
        """Use vibelint LLMs to determine optimal escape level."""
        try:
            # Prepare context for vibelint LLM
            focus_stack_context = []
            for i, focus in enumerate(stack["focus_process_stack"]):
                focus_stack_context.append({
                    "level": i + 1,
                    "focus_id": focus["focus_id"],
                    "description": focus["description"],
                    "started_at": focus["started_at"],
                    "branch_name": focus.get("branch_name"),
                    "parent_focus": focus.get("parent_focus")
                })

            vibelint_prompt = f"""
            FOCUS PROCESS ESCAPE ANALYSIS

            Current focus process stack (from bottom to top):
            {json.dumps(focus_stack_context, indent=2)}

            Escape reason: {reason}

            Circular dependency detected: {stack["circular_dependency_tracker"].get("detected", False)}
            Previous dependency chain: {stack["circular_dependency_tracker"].get("dependency_chain", [])}

            TASK: Determine the optimal number of stack levels to escape.

            Consider:
            1. Root cause of the issue requiring escape
            2. Which focus process in the stack is the problematic parent
            3. Minimum escape needed to break circular dependencies
            4. Impact on work progress vs. need to resolve conflicts

            Respond with ONLY a single integer representing the number of levels to escape:
            - 1 = Escape current focus only
            - 2+ = Escape multiple levels up the stack
            - 0 = Escape all levels (return to main branch)

            Your response:"""

            # Call vibelint LLM (placeholder for actual implementation)
            escape_levels = self._call_vibelint_llm(vibelint_prompt)

            if escape_levels is not None and isinstance(escape_levels, int):
                print(f"[FOCUS-MANAGER] Vibelint recommends escaping {escape_levels} level(s)")
                return escape_levels
            else:
                print("[FOCUS-MANAGER] Vibelint recommendation failed, using default (1 level)")
                return 1

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Vibelint escape recommendation failed: {e}")
            return 1  # Default to escaping one level

    def _call_vibelint_llm(self, prompt: str) -> Optional[int]:
        """
        Call vibelint LLM for escape recommendations.
        This integrates with the vibelint system to get intelligent decisions.
        """
        try:
            # Import vibelint config discovery
            vibelint_config = self._discover_vibelint_config()
            if not vibelint_config:
                print("[FOCUS-MANAGER] Vibelint not configured, using default escape level")
                return 1

            # Try to use vibelint's LLM configuration directly
            try:
                from vibelint.config import get_llm_client
                from vibelint.llm_utils import call_llm_with_prompt

                # Get the configured LLM client
                llm_client = get_llm_client(vibelint_config)

                # Call the LLM with our escape analysis prompt
                response = call_llm_with_prompt(
                    llm_client,
                    prompt,
                    max_tokens=50,
                    temperature=0.1
                )

                # Parse the response to extract escape level
                if response:
                    for line in response.strip().split('\n'):
                        line = line.strip()
                        if line.isdigit():
                            escape_level = int(line)
                            print(f"[FOCUS-MANAGER] Vibelint LLM recommends: {escape_level}")
                            return escape_level

            except ImportError:
                print("[FOCUS-MANAGER] Vibelint modules not available, falling back to subprocess")
                # Fallback to subprocess call
                return self._call_vibelint_subprocess(prompt, vibelint_config)

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Vibelint call failed: {e}")
            return None

    def _discover_vibelint_config(self) -> Optional[Dict[str, Any]]:
        """
        Discover vibelint configuration by walking up the directory tree.
        Uses the same discovery pattern as other linters.
        """
        config_names = ["vibelint.toml", "vibelint-distributed.toml", ".vibelint.toml"]

        # Start from project root and walk up
        current_dir = self.project_root
        while current_dir != current_dir.parent:
            for config_name in config_names:
                config_path = current_dir / config_name
                if config_path.exists():
                    try:
                        import tomllib
                        with open(config_path, 'rb') as f:
                            config = tomllib.load(f)
                        print(f"[FOCUS-MANAGER] Found vibelint config: {config_path}")
                        return config
                    except Exception as e:
                        print(f"[FOCUS-MANAGER-ERROR] Failed to load config {config_path}: {e}")
                        continue

            current_dir = current_dir.parent

        # Also check user home directory
        home_config = Path.home() / ".config" / "vibelint" / "config.toml"
        if home_config.exists():
            try:
                import tomllib
                with open(home_config, 'rb') as f:
                    config = tomllib.load(f)
                print(f"[FOCUS-MANAGER] Found user vibelint config: {home_config}")
                return config
            except Exception:
                pass

        return None

    def _call_vibelint_subprocess(self, prompt: str, config: Dict[str, Any]) -> Optional[int]:
        """
        Fallback to calling vibelint through subprocess when direct import fails.
        """
        try:
            # Create temporary prompt file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                # Call vibelint with escape analysis mode
                result = subprocess.run([
                    "python", "-m", "vibelint.distributed_linter",
                    "--mode", "focus-escape-analysis",
                    "--prompt-file", prompt_file
                ], cwd=self.project_root, capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    # Parse the response to get escape level
                    response = result.stdout.strip()
                    for line in response.split('\n'):
                        line = line.strip()
                        if line.isdigit():
                            return int(line)

                print(f"[FOCUS-MANAGER] Vibelint subprocess failed: {result.stderr}")

            finally:
                # Clean up temp file
                os.unlink(prompt_file)

        except subprocess.TimeoutExpired:
            print("[FOCUS-MANAGER] Vibelint call timed out")
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Vibelint subprocess failed: {e}")

        return None

    def auto_commit_tool_call(self, tool_name: str, file_paths: List[str],
                             description: str = None, tool_input: Dict[str, Any] = None) -> bool:
        """
        Auto-commit after each tool call with rich metadata for escape targeting.
        Each tool call becomes a commit, enabling precise git resets.
        """
        try:
            if not file_paths:
                return True  # No files to commit

            # Get current focus stack for metadata
            stack = self.load_focus_stack()
            focus_info = self.get_current_focus_info()
            current_focus = focus_info.get("focus_id")

            # Create rich commit message with metadata
            commit_msg = self._create_rich_commit_message(
                tool_name, file_paths, description, focus_info, stack, tool_input
            )

            # Add files and commit
            for file_path in file_paths:
                if os.path.exists(file_path):
                    subprocess.run(["git", "add", file_path],
                                 cwd=self.project_root, check=True)

            # Only commit if there are changes
            result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                  cwd=self.project_root, capture_output=True)

            if result.returncode != 0:  # There are staged changes
                subprocess.run(["git", "commit", "-m", commit_msg],
                             cwd=self.project_root, check=True)

                print(f"[FOCUS-MANAGER] Auto-committed: {tool_name}")

                # Update focus process with commit metadata
                self._update_focus_with_commit_metadata(current_focus, tool_name, file_paths)
                return True
            else:
                print(f"[FOCUS-MANAGER] No changes to commit for: {tool_name}")
                return True

        except subprocess.CalledProcessError as e:
            print(f"[FOCUS-MANAGER-ERROR] Auto-commit failed: {e}")
            return False
        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Auto-commit error: {e}")
            return False

    def _create_rich_commit_message(self, tool_name: str, file_paths: List[str],
                                   description: str, focus_info: Dict[str, Any],
                                   stack: Dict[str, Any], tool_input: Dict[str, Any] = None) -> str:
        """Create a commit message with rich metadata for escape targeting."""

        # Primary commit message
        if description:
            primary_msg = f"[{tool_name}] {description}"
        else:
            primary_msg = f"[{tool_name}] {', '.join(Path(p).name for p in file_paths)}"

        # Build metadata sections
        metadata_sections = []

        # Focus Process Context
        if focus_info.get("focus_id"):
            focus_section = f"""Focus-Process: {focus_info['focus_id']}
Focus-Description: {focus_info.get('description', 'No description')}
Focus-Stack-Depth: {focus_info.get('stack_depth', 0)}
Focus-Branch: {focus_info.get('branch_name', 'unknown')}"""
            metadata_sections.append(focus_section)

        # Stack Context for Escape Targeting
        if stack.get("focus_process_stack"):
            stack_chain = []
            for i, focus in enumerate(stack["focus_process_stack"]):
                stack_chain.append(f"  {i+1}. {focus['focus_id']} ({focus.get('branch_name', 'no-branch')})")

            stack_section = f"""Focus-Stack-Chain:
{chr(10).join(stack_chain)}"""
            metadata_sections.append(stack_section)

        # Tool Operation Details
        tool_section = f"""Tool-Operation: {tool_name}
Modified-Files: {', '.join(file_paths)}
Commit-Timestamp: {datetime.now().isoformat()}"""

        # Add tool-specific metadata
        if tool_input:
            tool_details = self._extract_tool_metadata(tool_name, tool_input)
            if tool_details:
                tool_section += f"\nTool-Details: {tool_details}"

        metadata_sections.append(tool_section)

        # Escape Targeting Metadata
        escape_section = f"""Escape-Targets:
  safe-point: {focus_info.get('focus_id', 'main')}
  parent-focus: {stack['focus_process_stack'][-2]['focus_id'] if len(stack.get('focus_process_stack', [])) > 1 else 'main'}
  root-focus: {stack['focus_process_stack'][0]['focus_id'] if stack.get('focus_process_stack') else 'main'}"""

        metadata_sections.append(escape_section)

        # Circular Dependency Context
        if stack.get("circular_dependency_tracker", {}).get("detected"):
            circular_section = f"""Circular-Dependency: DETECTED
Dependency-Chain: {', '.join(stack['circular_dependency_tracker'].get('dependency_chain', []))}
Escape-Hatch-Available: {stack['circular_dependency_tracker'].get('escape_hatch_triggered', False)}"""
            metadata_sections.append(circular_section)

        # Combine all sections
        full_message = primary_msg + "\n\n" + "\n\n".join(metadata_sections)

        # Add commit signature
        full_message += f"\n\nGenerated-By: focus-process-manager v1.0"

        return full_message

    def _extract_tool_metadata(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Extract tool-specific metadata for commit messages."""
        metadata_parts = []

        if tool_name == "Write":
            content_length = len(tool_input.get("content", ""))
            metadata_parts.append(f"content-length={content_length}")

            # Check if it's a new file or update
            file_path = tool_input.get("file_path", "")
            if file_path and not os.path.exists(file_path):
                metadata_parts.append("operation=create")
            else:
                metadata_parts.append("operation=update")

        elif tool_name == "Edit":
            old_string = tool_input.get("old_string", "")
            new_string = tool_input.get("new_string", "")
            replace_all = tool_input.get("replace_all", False)

            metadata_parts.append(f"old-length={len(old_string)}")
            metadata_parts.append(f"new-length={len(new_string)}")
            metadata_parts.append(f"replace-all={replace_all}")

        elif tool_name == "MultiEdit":
            edits = tool_input.get("edits", [])
            metadata_parts.append(f"edit-count={len(edits)}")

            total_old_chars = sum(len(edit.get("old_string", "")) for edit in edits)
            total_new_chars = sum(len(edit.get("new_string", "")) for edit in edits)
            metadata_parts.append(f"total-old-chars={total_old_chars}")
            metadata_parts.append(f"total-new-chars={total_new_chars}")

        elif tool_name == "NotebookEdit":
            cell_type = tool_input.get("cell_type", "unknown")
            edit_mode = tool_input.get("edit_mode", "replace")
            metadata_parts.append(f"cell-type={cell_type}")
            metadata_parts.append(f"edit-mode={edit_mode}")

        return ", ".join(metadata_parts) if metadata_parts else "basic-operation"

    def _update_focus_with_commit_metadata(self, focus_id: str, tool_name: str, file_paths: List[str]):
        """Update focus process with commit metadata for tracking."""
        try:
            stack = self.load_focus_stack()

            # Find current focus in stack and update metadata
            for focus in stack.get("focus_process_stack", []):
                if focus["focus_id"] == focus_id:
                    if "commit_history" not in focus:
                        focus["commit_history"] = []

                    # Get current commit hash
                    commit_hash = self._get_current_git_commit()

                    commit_record = {
                        "commit_hash": commit_hash,
                        "tool_name": tool_name,
                        "file_paths": file_paths,
                        "timestamp": datetime.now().isoformat(),
                        "focus_depth_at_commit": len(stack.get("focus_process_stack", []))
                    }

                    focus["commit_history"].append(commit_record)
                    break

            self.save_focus_stack(stack)

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to update focus commit metadata: {e}")

    def find_semantic_escape_target(self, reason: str, criteria: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Find the optimal escape target based on commit metadata and semantic analysis.

        Args:
            reason: The reason for escaping
            criteria: Optional criteria for escape target selection

        Returns:
            Dict containing escape recommendation with target info
        """
        try:
            stack = self.load_focus_stack()

            if not stack.get("focus_process_stack"):
                return {"target": "main", "levels": 0, "reason": "No focus processes active"}

            # Default criteria if not provided
            if criteria is None:
                criteria = {
                    "prefer_stable_commits": True,
                    "avoid_circular_dependencies": True,
                    "preserve_work": True,
                    "target_by_file_type": None,
                    "target_by_tool_type": None
                }

            # Analyze each focus level for escape suitability
            escape_candidates = []

            for i, focus in enumerate(stack["focus_process_stack"]):
                candidate = self._analyze_escape_candidate(focus, i, reason, criteria)
                escape_candidates.append(candidate)

            # Select the best escape target
            best_candidate = self._select_best_escape_target(escape_candidates, reason, criteria)

            return best_candidate

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Semantic escape targeting failed: {e}")
            return {"target": "current", "levels": 1, "reason": "Error in analysis, using safe default"}

    def _analyze_escape_candidate(self, focus: Dict[str, Any], level: int,
                                reason: str, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a focus process as an escape candidate."""
        candidate = {
            "focus_id": focus["focus_id"],
            "level": level,
            "escape_levels": len(focus.get("commit_history", [])) - level,  # How many levels to escape
            "stability_score": 0,
            "work_preservation_score": 0,
            "relevance_score": 0,
            "safety_score": 0,
            "commit_count": len(focus.get("commit_history", [])),
            "last_commit_time": focus.get("commit_history", [{}])[-1].get("timestamp") if focus.get("commit_history") else None,
            "branch_name": focus.get("branch_name"),
            "git_commit_before": focus.get("git_commit_before")
        }

        # Calculate stability score based on commit patterns
        commit_history = focus.get("commit_history", [])
        if commit_history:
            # More commits = more stable
            candidate["stability_score"] += min(len(commit_history) * 10, 50)

            # Recent activity = more relevant
            if candidate["last_commit_time"]:
                from datetime import datetime, timedelta
                last_time = datetime.fromisoformat(candidate["last_commit_time"])
                hours_ago = (datetime.now() - last_time).total_seconds() / 3600
                if hours_ago < 1:
                    candidate["relevance_score"] += 30
                elif hours_ago < 24:
                    candidate["relevance_score"] += 20
                else:
                    candidate["relevance_score"] += 10

            # Analyze commit types for work preservation
            tool_types = [commit.get("tool_name") for commit in commit_history]
            if "Write" in tool_types:
                candidate["work_preservation_score"] += 20  # New files created
            if "Edit" in tool_types or "MultiEdit" in tool_types:
                candidate["work_preservation_score"] += 15  # Existing work modified

        # Safety score based on circular dependency risk
        if focus["focus_id"] not in reason.lower():  # Not directly related to the problem
            candidate["safety_score"] += 20

        # Bonus for being a "clean" focus (no circular dependencies detected when created)
        if not focus.get("circular_dependency_detected_on_creation", False):
            candidate["safety_score"] += 15

        return candidate

    def _select_best_escape_target(self, candidates: List[Dict[str, Any]],
                                 reason: str, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Select the best escape target from analyzed candidates."""

        if not candidates:
            return {"target": "main", "levels": 0, "reason": "No candidates available"}

        # Score each candidate
        for candidate in candidates:
            total_score = 0

            if criteria.get("prefer_stable_commits", True):
                total_score += candidate["stability_score"] * 1.2

            if criteria.get("preserve_work", True):
                total_score += candidate["work_preservation_score"] * 1.5

            if criteria.get("avoid_circular_dependencies", True):
                total_score += candidate["safety_score"] * 1.0

            total_score += candidate["relevance_score"] * 0.8

            candidate["total_score"] = total_score

        # Sort by total score (highest first)
        candidates.sort(key=lambda x: x["total_score"], reverse=True)

        best = candidates[0]

        # Determine escape strategy
        if best["total_score"] < 20:  # Very low score, escape to main
            return {
                "target": "main",
                "levels": 0,
                "focus_id": None,
                "branch": "main",
                "commit_hash": None,
                "reason": f"Low confidence in stack stability (score: {best['total_score']:.1f})",
                "candidates_analyzed": len(candidates)
            }

        return {
            "target": best["focus_id"],
            "levels": len(candidates) - best["level"],
            "focus_id": best["focus_id"],
            "branch": best["branch_name"],
            "commit_hash": best["git_commit_before"],
            "reason": f"Best target with score {best['total_score']:.1f} (stability: {best['stability_score']}, work: {best['work_preservation_score']}, safety: {best['safety_score']})",
            "candidates_analyzed": len(candidates),
            "commit_count_at_target": best["commit_count"]
        }

    def complete_current_focus(self, merge_strategy: str = "auto") -> bool:
        """
        Complete the current focus process with merge.

        Args:
            merge_strategy: "auto", "squash", "merge", or "no-merge"

        Returns:
            True if focus was successfully completed and merged
        """
        try:
            focus_info = self.get_current_focus_info()
            current_focus = focus_info.get('focus_id')

            if not current_focus:
                print("[FOCUS-MANAGER] No active focus process to complete")
                return False

            print(f"[FOCUS-MANAGER] Completing focus process: {current_focus}")

            # Use pop_focus_process with merge (not escape)
            success = self.pop_focus_process(force_escape=False, merge_strategy=merge_strategy)

            if success:
                print(f"[FOCUS-MANAGER] Successfully completed and merged focus: {current_focus}")
            else:
                print(f"[FOCUS-MANAGER] Failed to complete focus: {current_focus}")

            return success

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Focus completion error: {e}")
            return False

    def force_remote_push(self, branch: str = None) -> bool:
        """
        Force a push to remote repository regardless of timing.

        Args:
            branch: Branch to push (defaults to current branch)

        Returns:
            True if push was successful
        """
        try:
            if branch is None:
                branch = self._get_current_branch()

            if not branch:
                print("[FOCUS-MANAGER-ERROR] No branch to push")
                return False

            print(f"[FOCUS-MANAGER] Force pushing {branch} to remote...")

            # Push to remote
            result = subprocess.run([
                "git", "push", "origin", branch
            ], cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"[FOCUS-MANAGER] Successfully force pushed {branch}")
                self._update_last_push_time()
                return True
            else:
                print(f"[FOCUS-MANAGER-ERROR] Force push failed: {result.stderr}")
                return False

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Force push error: {e}")
            return False

    def escape_to_semantic_target(self, reason: str, criteria: Dict[str, Any] = None) -> bool:
        """
        Perform escape to semantically determined target based on commit metadata.
        """
        try:
            # Find the best escape target
            target_info = self.find_semantic_escape_target(reason, criteria)

            print(f"[FOCUS-MANAGER] Semantic escape analysis:")
            print(f"  Target: {target_info['target']}")
            print(f"  Levels to escape: {target_info['levels']}")
            print(f"  Reason: {target_info['reason']}")

            # Perform the escape
            if target_info["levels"] == 0:
                # Escape all the way to main
                return self.trigger_escape_hatch(
                    f"Semantic escape: {reason} -> {target_info['reason']}",
                    escape_levels=0,
                    use_vibelint_judge=False
                )
            else:
                # Escape to specific level
                return self.trigger_escape_hatch(
                    f"Semantic escape: {reason} -> {target_info['reason']}",
                    escape_levels=target_info["levels"],
                    use_vibelint_judge=False
                )

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Semantic escape failed: {e}")
            # Fallback to single level escape
            return self.trigger_escape_hatch(
                f"Fallback escape due to error: {e}",
                escape_levels=1,
                use_vibelint_judge=False
            )

    def _detect_circular_dependency(self, stack: Dict[str, Any], new_focus_id: str) -> bool:
        """Detect if adding new focus would create circular dependency."""
        current_chain = [process["focus_id"] for process in stack["focus_process_stack"]]
        return new_focus_id in current_chain

    def _get_current_git_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _create_git_branch(self, branch_name: str) -> bool:
        """Create and switch to a new git branch."""
        try:
            # Create and switch to new branch
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def _switch_git_branch(self, branch_name: str) -> bool:
        """Switch to an existing git branch."""
        try:
            result = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def _auto_commit_changes(self, commit_message: str) -> bool:
        """Auto-commit current changes."""
        try:
            # Add all changes
            subprocess.run(["git", "add", "."], cwd=self.project_root, check=True)

            # Commit with message
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.project_root,
                check=True
            )
            return True
        except Exception:
            return False

    def _revert_to_git_commit(self, commit_hash: str) -> bool:
        """Revert to a specific git commit."""
        try:
            result = subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_current_focus_info(self) -> Dict[str, Any]:
        """Get information about the current focus process."""
        stack = self.load_focus_stack()

        if not stack["focus_process_stack"]:
            return {"focus_id": None, "description": "", "stack_depth": 0}

        current_focus = stack["focus_process_stack"][-1]
        return {
            "focus_id": current_focus["focus_id"],
            "description": current_focus["description"],
            "stack_depth": len(stack["focus_process_stack"]),
            "branch_name": current_focus.get("branch_name"),
            "auto_commit": current_focus.get("auto_commit_on_edit", False),
            "circular_dependency_detected": stack["circular_dependency_tracker"]["detected"]
        }

    def reset_override_usage(self, override_type: str = None, reason: str = "focus_manager_reset") -> bool:
        """
        Reset override usage counters through the focus process manager.
        This provides Claude with a direct way to reset override tracking.

        Args:
            override_type: Specific override to reset ('emoji_check', 'git_operations', etc.) or None for all
            reason: Reason for the reset

        Returns:
            True if reset was successful
        """
        try:
            from .override_usage_tracker import get_override_tracker
            tracker = get_override_tracker()

            success = tracker.reset_override_usage(override_type, reason)

            if success:
                if override_type:
                    print(f"[FOCUS-MANAGER] Reset override usage for: {override_type}")
                else:
                    print("[FOCUS-MANAGER] Reset all override usage counters")

            return success

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to reset override usage: {e}")
            return False

    def get_override_usage_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current override usage patterns.
        Useful for Claude to understand override usage state.

        Returns:
            Dict containing override usage summary
        """
        try:
            from .override_usage_tracker import get_override_tracker
            tracker = get_override_tracker()

            return tracker.get_usage_summary()

        except Exception as e:
            print(f"[FOCUS-MANAGER-ERROR] Failed to get override summary: {e}")
            return {"error": str(e)}