#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Tree-based work management system.

Tracks work as a tree structure to prevent getting sidetracked and losing
the main thread. Also checks for project root hygiene violations.

Key features:
- Track current work context and branching
- Remember parent work when switching contexts
- Detect root directory clutter (vibe failures)
- Provide clean work resumption suggestions
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

def get_project_root() -> Path:
    """Find the project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

class WorkTreeNode:
    """Represents a node in the work tree."""

    def __init__(self, task_id: str, description: str, parent_id: Optional[str] = None):
        self.task_id = task_id
        self.description = description
        self.parent_id = parent_id
        self.children: List[str] = []
        self.status = "active"  # active, paused, completed, abandoned
        self.created_at = datetime.now().isoformat()
        self.context = {
            "files_being_worked_on": [],
            "key_decisions_made": [],
            "next_steps": [],
            "blockers": []
        }
        self.completion_criteria = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "parent_id": self.parent_id,
            "children": self.children,
            "status": self.status,
            "created_at": self.created_at,
            "context": self.context,
            "completion_criteria": self.completion_criteria
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkTreeNode':
        node = cls(data["task_id"], data["description"], data.get("parent_id"))
        node.children = data.get("children", [])
        node.status = data.get("status", "active")
        node.created_at = data.get("created_at", datetime.now().isoformat())
        node.context = data.get("context", {})
        node.completion_criteria = data.get("completion_criteria", [])
        return node

class WorkTreeManager:
    """Manages the tree of work contexts."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.work_file = project_root / '.claude' / 'work-tree.json'
        self.work_file.parent.mkdir(exist_ok=True)

        self.nodes: Dict[str, WorkTreeNode] = {}
        self.current_task_id: Optional[str] = None
        self.load_work_tree()

    def load_work_tree(self):
        """Load existing work tree."""
        if self.work_file.exists():
            try:
                with open(self.work_file, 'r') as f:
                    data = json.load(f)

                self.current_task_id = data.get("current_task_id")

                for node_data in data.get("nodes", []):
                    node = WorkTreeNode.from_dict(node_data)
                    self.nodes[node.task_id] = node

            except (json.JSONDecodeError, KeyError):
                self.initialize_empty_tree()
        else:
            self.initialize_empty_tree()

    def initialize_empty_tree(self):
        """Initialize with a root task."""
        root_task = WorkTreeNode(
            "root",
            "Main development work",
            None
        )
        self.nodes["root"] = root_task
        self.current_task_id = "root"

    def save_work_tree(self):
        """Save work tree to file."""
        data = {
            "current_task_id": self.current_task_id,
            "last_updated": datetime.now().isoformat(),
            "nodes": [node.to_dict() for node in self.nodes.values()]
        }

        with open(self.work_file, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def get_current_task(self) -> Optional[WorkTreeNode]:
        """Get the current active task."""
        if self.current_task_id and self.current_task_id in self.nodes:
            return self.nodes[self.current_task_id]
        return None

    def detect_context_switch(self) -> Optional[str]:
        """Detect if we're switching work contexts based on recent activity."""
        tool_name = os.environ.get('CLAUDE_TOOL_NAME', '')
        file_paths = os.environ.get('CLAUDE_FILE_PATHS', '').split(',')
        file_paths = [f.strip() for f in file_paths if f.strip()]

        current_task = self.get_current_task()
        if not current_task:
            return None

        # Check if we're working on completely different files
        current_files = set(current_task.context.get("files_being_worked_on", []))
        new_files = set(file_paths)

        if current_files and new_files and not (current_files & new_files):
            # No overlap in files - potential context switch
            return f"Working on different files: {', '.join(new_files)}"

        # Check for specific context switch indicators
        switch_indicators = [
            ("DEVELOPMENT_METHODOLOGY.md", "methodology_work"),
            ("VIBELINT_WORKFLOWS.md", "workflow_design"),
            ("AGENTS.instructions.md", "instruction_updates"),
            (".claude/hooks/", "hook_development"),
            ("progress", "progress_tracking"),
            ("README.md", "documentation")
        ]

        for file_path in file_paths:
            for indicator, context_name in switch_indicators:
                if indicator in file_path:
                    if current_task.task_id != context_name:
                        return f"Context switch to {context_name}"

        return None

    def suggest_work_tree_action(self) -> Dict[str, Any]:
        """Suggest what to do with the work tree based on current state."""
        current_task = self.get_current_task()
        context_switch = self.detect_context_switch()

        suggestion = {
            "action": "continue",
            "message": "Continuing current work",
            "options": []
        }

        if context_switch:
            suggestion["action"] = "branch"
            suggestion["message"] = f"Detected context switch: {context_switch}"
            suggestion["options"] = [
                "Create new branch task for this work",
                "Mark current task as paused and switch context",
                "Continue current task (ignore context switch)"
            ]

        # Check if current task should be completed
        if current_task and current_task.completion_criteria:
            completed_criteria = []
            for criteria in current_task.completion_criteria:
                # Simple completion checking - could be enhanced
                if any(keyword in criteria.lower() for keyword in ["file created", "hook added"]):
                    completed_criteria.append(criteria)

            if len(completed_criteria) >= len(current_task.completion_criteria) * 0.7:
                suggestion["action"] = "complete"
                suggestion["message"] = f"Task '{current_task.description}' appears ready for completion"
                suggestion["options"] = [
                    "Mark task as completed and return to parent",
                    "Continue with additional work",
                    "Create follow-up task"
                ]

        return suggestion

def check_root_directory_hygiene() -> Dict[str, Any]:
    """Check for root directory clutter (vibe failures)."""
    project_root = get_project_root()

    # Define what should and shouldn't be in project root
    allowed_patterns = {
        # Build/config files
        "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "Makefile",
        "package.json", "package-lock.json", "yarn.lock",
        "Cargo.toml", "Cargo.lock",

        # Documentation
        "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md",
        "MANIFEST.in",

        # VCS
        ".git", ".gitignore", ".gitmodules",

        # CI/CD
        ".github", ".gitlab-ci.yml", "Jenkinsfile",

        # IDE
        ".vscode", ".idea",

        # Project structure
        "src", "tests", "docs", "tools", "examples",

        # Project-specific
        "AGENTS.instructions.md", "DEVELOPMENT_METHODOLOGY.md",
        "AUTOMATED_DEVELOPMENT_WORKFLOW.md"
    }

    # Things that shouldn't be in root
    clutter_patterns = {
        # Cache/temp files
        "*.pyc", "__pycache__", "*.pyo", "*.pyd", ".Python",
        ".coverage", "coverage.xml", "htmlcov",
        ".tox", ".cache", ".pytest_cache",
        ".ruff_cache", ".mypy_cache",
        "node_modules", ".npm",

        # Build artifacts
        "build", "dist", "*.egg-info",
        "target", # Rust

        # IDE artifacts
        "*.swp", "*.swo", "*~", ".DS_Store",

        # Project-specific clutter
        ".vibelint-reports", ".vibelint-self-improvement",
        ".vibelint-cache", ".vibelint-progress"
    }

    violations = []
    root_items = list(project_root.iterdir())

    for item in root_items:
        item_name = item.name

        # Check if it's allowed
        if item_name in allowed_patterns:
            continue

        # Check if it matches clutter patterns
        is_clutter = False
        for pattern in clutter_patterns:
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(item_name, pattern):
                    is_clutter = True
                    break
            elif item_name == pattern:
                is_clutter = True
                break

        if is_clutter:
            violations.append({
                "type": "clutter",
                "path": str(item),
                "suggestion": f"Move {item_name} to appropriate subdirectory or .gitignore"
            })
        elif not item_name.startswith('.') and item.is_file():
            # Unexpected file in root
            violations.append({
                "type": "unexpected_file",
                "path": str(item),
                "suggestion": f"Consider moving {item_name} to docs/ or appropriate subdirectory"
            })

    return {
        "violations": violations,
        "total_items": len(root_items),
        "clean": len(violations) == 0
    }

def generate_work_summary() -> str:
    """Generate a clean work summary."""
    project_root = get_project_root()
    manager = WorkTreeManager(project_root)

    current_task = manager.get_current_task()
    suggestion = manager.suggest_work_tree_action()
    hygiene = check_root_directory_hygiene()

    summary = ["🌳 Work Tree Status:"]

    if current_task:
        summary.append(f"Current: {current_task.description} ({current_task.status})")

        if current_task.context.get("next_steps"):
            summary.append("Next Steps:")
            for step in current_task.context["next_steps"][:3]:
                summary.append(f"  - {step}")

    # Work tree suggestion
    if suggestion["action"] != "continue":
        summary.append(f"\n💡 Suggestion: {suggestion['message']}")

    # Root hygiene
    if not hygiene["clean"]:
        summary.append(f"\n🧹 Root Directory Issues: {len(hygiene['violations'])} violations")
        for violation in hygiene["violations"][:3]:
            summary.append(f"  - {violation['type']}: {Path(violation['path']).name}")
        if len(hygiene["violations"]) > 3:
            summary.append(f"  ... and {len(hygiene['violations']) - 3} more")

    return '\n'.join(summary)

def main():
    """Main work tree management function."""
    try:
        project_root = get_project_root()
        manager = WorkTreeManager(project_root)

        # Update current task context
        current_task = manager.get_current_task()
        if current_task:
            file_paths = os.environ.get('CLAUDE_FILE_PATHS', '').split(',')
            file_paths = [f.strip() for f in file_paths if f.strip()]

            if file_paths:
                current_files = set(current_task.context.get("files_being_worked_on", []))
                current_files.update(file_paths)
                current_task.context["files_being_worked_on"] = list(current_files)

        # Check for context switches and hygiene issues
        suggestion = manager.suggest_work_tree_action()
        hygiene = check_root_directory_hygiene()

        # Save updated state
        manager.save_work_tree()

        # Output summary if there are issues
        if suggestion["action"] != "continue" or not hygiene["clean"]:
            print(generate_work_summary())

            # Suggest cleanup commands for hygiene violations
            if not hygiene["clean"]:
                print("\n🛠️  Quick cleanup commands:")
                for violation in hygiene["violations"][:5]:
                    path = violation["path"]
                    if "cache" in path or "coverage" in path or ".tox" in path:
                        print(f"  rm -rf {path}")
                    elif violation["type"] == "unexpected_file":
                        print(f"  # Consider: mv {path} docs/ or appropriate location")

    except Exception as e:
        # Log error but don't break development flow
        error_log = project_root / '.claude' / 'work-tree-errors.log'
        with open(error_log, 'a') as f:
            f.write(f"{datetime.now().isoformat()}: {str(e)}\n")

if __name__ == '__main__':
    main()