"""Utility functions for kaia-guardrails."""

from pathlib import Path


def find_agents_files(project_root: Path) -> list[Path]:
    """Find all AGENTS.*.md files in project root.

    Args:
        project_root: Project root directory

    Returns:
        List of AGENTS.*.md file paths, sorted by name
    """
    return sorted(project_root.glob("AGENTS.*.md"))


def read_all_agents_content(project_root: Path) -> str:
    """Read and concatenate all AGENTS.*.md files.

    Args:
        project_root: Project root directory

    Returns:
        Concatenated content of all AGENTS files
    """
    agents_files = find_agents_files(project_root)
    if not agents_files:
        return ""

    content_parts = []
    for agent_file in agents_files:
        with open(agent_file) as f:
            content_parts.append(f"# {agent_file.name}\n\n{f.read()}")

    return "\n\n---\n\n".join(content_parts)
