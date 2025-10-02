"""
Test cases for the focus process management system.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from kaia_guardrails.hooks.implementation.focus_process_manager import \
    FocusProcessManager


class TestFocusProcessManager:
    """Test cases for FocusProcessManager."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir()

        # Create a fake git directory
        git_dir = temp_dir / ".git"
        git_dir.mkdir()

        yield temp_dir

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def manager(self, temp_project_dir):
        """Create a FocusProcessManager instance for testing."""
        return FocusProcessManager(project_root=temp_project_dir)

    def test_initial_state(self, manager):
        """Test the initial state of the focus process manager."""
        focus_info = manager.get_current_focus_info()

        assert focus_info["focus_id"] is None
        assert focus_info["description"] == ""
        assert focus_info["stack_depth"] == 0

    def test_push_focus_process(self, manager):
        """Test pushing a focus process onto the stack."""
        # Push first focus process
        success = manager.push_focus_process(
            "test_focus",
            "Testing focus process functionality",
            create_branch=False,
            auto_commit=False,
        )

        assert success is True

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] == "test_focus"
        assert focus_info["description"] == "Testing focus process functionality"
        assert focus_info["stack_depth"] == 1

    def test_nested_focus_processes(self, manager):
        """Test pushing multiple nested focus processes."""
        # Push first focus
        manager.push_focus_process(
            "parent_focus", "Parent focus process", create_branch=False, auto_commit=False
        )

        # Push nested focus
        manager.push_focus_process(
            "child_focus", "Child focus process", create_branch=False, auto_commit=False
        )

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] == "child_focus"
        assert focus_info["stack_depth"] == 2

    def test_circular_dependency_detection(self, manager):
        """Test circular dependency detection."""
        # Push first focus
        manager.push_focus_process("focus_a", "Focus A", create_branch=False, auto_commit=False)

        # Push second focus
        manager.push_focus_process("focus_b", "Focus B", create_branch=False, auto_commit=False)

        # Try to push focus_a again (should fail due to circular dependency)
        success = manager.push_focus_process(
            "focus_a", "This should fail", create_branch=False, auto_commit=False
        )

        assert success is False

        focus_info = manager.get_current_focus_info()
        assert focus_info["circular_dependency_detected"] is True

    def test_pop_focus_process(self, manager):
        """Test popping focus processes from the stack."""
        # Push two focus processes
        manager.push_focus_process("focus_1", "First focus", create_branch=False, auto_commit=False)

        manager.push_focus_process(
            "focus_2", "Second focus", create_branch=False, auto_commit=False
        )

        # Pop the second focus
        success = manager.pop_focus_process()
        assert success is True

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] == "focus_1"
        assert focus_info["stack_depth"] == 1

        # Pop the first focus
        success = manager.pop_focus_process()
        assert success is True

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] is None
        assert focus_info["stack_depth"] == 0

    def test_escape_hatch(self, manager):
        """Test the escape hatch functionality."""
        # Push a focus process
        manager.push_focus_process(
            "escape_test", "Testing escape hatch", create_branch=False, auto_commit=False
        )

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] == "escape_test"

        # Trigger escape hatch
        success = manager.trigger_escape_hatch("Testing escape mechanism")
        assert success is True

        focus_info = manager.get_current_focus_info()
        assert focus_info["focus_id"] is None

    def test_empty_stack_operations(self, manager):
        """Test operations on an empty stack."""
        # Try to pop from empty stack
        success = manager.pop_focus_process()
        assert success is False

        # Try to escape from empty stack
        success = manager.trigger_escape_hatch("No focus to escape from")
        assert success is False

    def test_stack_persistence(self, manager):
        """Test that focus stack persists across manager instances."""
        # Push a focus with first manager instance
        manager.push_focus_process(
            "persistent_focus", "Testing persistence", create_branch=False, auto_commit=False
        )

        # Create new manager instance with same project root
        new_manager = FocusProcessManager(project_root=manager.project_root)

        # Check that focus persists
        focus_info = new_manager.get_current_focus_info()
        assert focus_info["focus_id"] == "persistent_focus"
        assert focus_info["description"] == "Testing persistence"

    @patch("subprocess.run")
    def test_git_operations_disabled(self, mock_subprocess, manager):
        """Test that git operations can be disabled for testing."""
        # This test ensures our git operations don't break when disabled
        success = manager.push_focus_process(
            "git_test",
            "Testing without git",
            create_branch=False,  # Explicitly disable git
            auto_commit=False,
        )

        assert success is True
        # Subprocess should not be called when git is disabled
        mock_subprocess.assert_not_called()

    def test_focus_stack_data_structure(self, manager):
        """Test the internal data structure of the focus stack."""
        manager.push_focus_process(
            "structure_test", "Testing data structure", create_branch=False, auto_commit=True
        )

        stack_data = manager.load_focus_stack()

        # Check required fields
        assert "current_focus" in stack_data
        assert "focus_process_stack" in stack_data
        assert "circular_dependency_tracker" in stack_data
        assert "branching_strategy" in stack_data

        # Check focus entry structure
        focus_entry = stack_data["focus_process_stack"][0]
        required_fields = [
            "focus_id",
            "description",
            "started_at",
            "parent_focus",
            "escape_hatch_available",
        ]

        for field in required_fields:
            assert field in focus_entry
