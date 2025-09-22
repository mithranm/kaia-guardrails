#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Progress tracking hook for vibelint development.

Tracks progress against DEVELOPMENT_METHODOLOGY.md requirements and workflows.
Simplified - no need for extensive exception handling with safe wrapper.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

def get_project_root() -> Path:
    """Find the vibelint project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / 'pyproject.toml').exists() and 'vibelint' in current.name:
            return current
        current = current.parent
    return Path.cwd()

def load_progress_state() -> Dict[str, Any]:
    """Load existing progress state."""
    progress_file = get_project_root() / '.vibelint-progress' / 'development-progress.json'
    progress_file.parent.mkdir(exist_ok=True)

    if progress_file.exists():
        try:
            with open(progress_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    return {
        'session_id': datetime.now().isoformat(),
        'workflows': {
            'workflow_1_single_file_validation': {'status': 'not_started', 'completion': 0},
            'workflow_2_multi_representation_analysis': {'status': 'not_started', 'completion': 0},
            'workflow_3_deterministic_fixes': {'status': 'not_started', 'completion': 0},
            'workflow_4_watch_mode': {'status': 'not_started', 'completion': 0},
            'workflow_5_smoke_testing': {'status': 'not_started', 'completion': 0},
            'workflow_6_validator_extension': {'status': 'not_started', 'completion': 0},
            'workflow_7_experimental_branches': {'status': 'not_started', 'completion': 0}
        },
        'methodology_compliance': {
            'requirements_defined': False,
            'human_decision_points_identified': False,
            'acceptance_criteria_clear': False,
            'testing_strategy_defined': False
        },
        'tool_calls': [],
        'last_updated': datetime.now().isoformat()
    }

def save_progress_state(progress_data: Dict[str, Any]):
    """Save progress state."""
    progress_file = get_project_root() / '.vibelint-progress' / 'development-progress.json'
    progress_file.parent.mkdir(exist_ok=True)
    
    with open(progress_file, 'w') as f:
        json.dump(progress_data, f, indent=2)

def analyze_tool_call_impact(tool_name: str, file_paths: List[str]) -> Dict[str, Any]:
    """Analyze the impact of a tool call on development progress."""
    impact = {
        'workflow_affected': None,
        'progress_delta': 0,
        'methodology_updates': []
    }

    # Analyze which workflow is being worked on based on file paths
    for file_path in file_paths:
        if 'single_file_validation' in file_path or 'self_validation' in file_path:
            impact['workflow_affected'] = 'workflow_1_single_file_validation'
            if tool_name in ['write', 'edit', 'patch']:
                impact['progress_delta'] = 5  # Small progress increment
        elif 'multi_representation' in file_path or 'analysis' in file_path:
            impact['workflow_affected'] = 'workflow_2_multi_representation_analysis'
            if tool_name in ['write', 'edit', 'patch']:
                impact['progress_delta'] = 5
        elif 'deterministic' in file_path or 'fixes' in file_path:
            impact['workflow_affected'] = 'workflow_3_deterministic_fixes'
            if tool_name in ['write', 'edit', 'patch']:
                impact['progress_delta'] = 5
        elif 'watch' in file_path or 'monitor' in file_path:
            impact['workflow_affected'] = 'workflow_4_watch_mode'
            if tool_name in ['write', 'edit', 'patch']:
                impact['progress_delta'] = 5

    return impact

def generate_progress_summary(progress_data: Dict[str, Any]) -> str:
    """Generate a human-readable progress summary."""
    workflows = progress_data.get('workflows', {})
    total_workflows = len(workflows)
    
    if total_workflows == 0:
        return "📊 No workflow progress data available"

    completed = sum(1 for w in workflows.values() if w.get('status') == 'completed')
    in_progress = sum(1 for w in workflows.values() if w.get('status') == 'in_progress')
    not_started = sum(1 for w in workflows.values() if w.get('status') == 'not_started')

    summary = [
        "📊 Vibelint Development Progress:",
        f"  ✅ Completed: {completed}/{total_workflows} workflows",
        f"  🔄 In Progress: {in_progress}/{total_workflows} workflows",
        f"  ⏳ Not Started: {not_started}/{total_workflows} workflows"
    ]

    # Show active workflows
    active_workflows = [name for name, data in workflows.items() 
                      if data.get('status') == 'in_progress']
    if active_workflows:
        summary.append("  🎯 Currently working on:")
        for workflow in active_workflows:
            completion = workflows[workflow].get('completion', 0)
            display_name = workflow.replace('_', ' ').title()
            summary.append(f"    - {display_name}: {completion}% complete")

    methodology = progress_data.get('methodology_compliance', {})
    compliance_count = sum(1 for v in methodology.values() if v)
    total_compliance = len(methodology)
    
    if total_compliance > 0:
        summary.append(f"  📋 Methodology Compliance: {compliance_count}/{total_compliance} items")

    return '\n'.join(summary)

def main():
    """Main progress tracking function."""
    # Get tool call information
    tool_name = os.environ.get('CLAUDE_TOOL_NAME', 'unknown')
    file_paths = os.environ.get('CLAUDE_FILE_PATHS', '').split(',') if os.environ.get('CLAUDE_FILE_PATHS') else []
    
    # Skip tracking for certain tools
    skip_tools = ['read', 'list', 'get_file_info']
    if tool_name.lower() in skip_tools:
        return

    print(f"[VIBELINT-PROGRESS] Tracking progress for tool: {tool_name}", file=sys.stderr)

    # Load current progress
    progress_data = load_progress_state()

    # Analyze tool call impact
    impact = analyze_tool_call_impact(tool_name, file_paths)

    # Update progress based on impact
    if impact.get('workflow_affected'):
        workflow_name = impact['workflow_affected']
        if workflow_name in progress_data['workflows']:
            current_completion = progress_data['workflows'][workflow_name].get('completion', 0)
            new_completion = min(100, current_completion + impact.get('progress_delta', 0))
            progress_data['workflows'][workflow_name]['completion'] = new_completion
            
            # Update status based on completion
            if new_completion > 0 and progress_data['workflows'][workflow_name]['status'] == 'not_started':
                progress_data['workflows'][workflow_name]['status'] = 'in_progress'
            elif new_completion >= 100:
                progress_data['workflows'][workflow_name]['status'] = 'completed'

    # Record tool call
    tool_call_record = {
        'timestamp': datetime.now().isoformat(),
        'tool_name': tool_name,
        'file_paths': file_paths,
        'impact': impact
    }
    
    if 'tool_calls' not in progress_data:
        progress_data['tool_calls'] = []
    progress_data['tool_calls'].append(tool_call_record)
    
    # Keep only last 50 tool calls
    progress_data['tool_calls'] = progress_data['tool_calls'][-50:]
    
    progress_data['last_updated'] = datetime.now().isoformat()

    # Save updated progress
    save_progress_state(progress_data)

    # Generate and report summary for significant changes
    if impact.get('progress_delta', 0) > 0:
        summary = generate_progress_summary(progress_data)
        print(f"[VIBELINT-PROGRESS] Development progress updated:\n{summary}", file=sys.stderr)

if __name__ == '__main__':
    main()
