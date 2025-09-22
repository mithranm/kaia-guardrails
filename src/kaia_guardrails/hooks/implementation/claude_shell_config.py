#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Claude Code Shell Configuration Hook

This hook addresses Claude Code's limitation with shell configuration loading.
It provides mechanisms to ensure shell environment (aliases, functions, PATH) 
is properly available when Claude Code executes bash commands.

Based on issue: https://github.com/anthropics/claude-code/issues/1630
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any

from kaia_guardrails.hooks.base import HookBase, HookError


class ClaudeShellConfigHook(HookBase):
    """Hook to help Claude Code access proper shell configuration."""
    
    def __init__(self, name: str = "claude-shell-config", **kwargs):
        super().__init__(name=name, **kwargs)
    
    def run(self, context: Dict[str, Any]) -> Any:
        """
        Set up shell configuration helpers for Claude Code.
        
        This hook creates helper scripts and environment configurations
        to work around Claude Code's shell configuration limitations.
        """
        try:
            project_root = self._find_project_root()
            claude_dir = project_root / ".claude"
            claude_dir.mkdir(exist_ok=True)
            
            # Create a shell helper script that sources zshrc
            self._create_shell_helper(claude_dir)
            
            # Create a Claude Code configuration snippet
            self._create_claude_config(claude_dir)
            
            # Update CLAUDE.md with shell configuration instructions
            self._update_claude_md(project_root)
            
            return {
                "status": "success",
                "helpers_created": [
                    str(claude_dir / "shell-helper.sh"),
                    str(claude_dir / "shell-config.md")
                ]
            }
            
        except Exception as e:
            raise HookError(f"Failed to set up Claude shell configuration: {e}")
    
    def _find_project_root(self) -> Path:
        """Find the project root directory."""
        current = Path.cwd()
        while current.parent != current:
            if (current / '.git').exists() or (current / 'pyproject.toml').exists():
                return current
            current = current.parent
        return Path.cwd()
    
    def _create_shell_helper(self, claude_dir: Path):
        """Create a shell helper script that properly sources configuration."""
        helper_script = claude_dir / "shell-helper.sh"
        
        content = '''#!/bin/zsh
# Claude Code Shell Helper
# This script sources your shell configuration before running commands
# Usage: source .claude/shell-helper.sh && your_command

# Source zsh configuration if it exists
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc"
fi

# Source bash configuration as fallback
if [ -f "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc"
fi

# Verify common tools are available
echo "Shell configuration loaded. Available tools:"
if command -v git >/dev/null 2>&1; then echo "✓ git"; fi
if command -v node >/dev/null 2>&1; then echo "✓ node"; fi
if command -v python >/dev/null 2>&1; then echo "✓ python"; fi
if command -v conda >/dev/null 2>&1; then echo "✓ conda"; fi

# Show current PATH
echo "Current PATH: $PATH"
'''
        
        helper_script.write_text(content)
        helper_script.chmod(0o755)
    
    def _create_claude_config(self, claude_dir: Path):
        """Create Claude Code configuration documentation."""
        config_file = claude_dir / "shell-config.md"
        
        content = '''# Shell Configuration for Claude Code

## Problem
Claude Code doesn't load shell configuration (.zshrc, .bashrc) by default,
causing issues with aliases, functions, and custom PATH configurations.

## Solutions

### 1. Use the Shell Helper
For commands that need your full shell environment:
```bash
source .claude/shell-helper.sh && your_command
```

### 2. Explicit Configuration Loading
For one-off commands:
```bash
zsh -c 'source ~/.zshrc && your_command'
```

### 3. Environment Variables
Set important environment variables in Claude Code settings:
- Add to `.claude/settings.json`:
```json
{
  "env": {
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"
  }
}
```

### 4. Use Full Paths
When aliases/functions don't work, use full paths:
```bash
/usr/local/bin/node instead of just node
```

## Troubleshooting

### Missing Commands
If you get "command not found" errors:
1. Check if the command exists: `which command_name`
2. Use full path: `/full/path/to/command`
3. Source shell config first: `source .claude/shell-helper.sh`

### PATH Issues
If your PATH seems wrong:
1. Check current PATH: `echo $PATH`
2. Compare with normal terminal: `echo $PATH` in regular terminal
3. Source your configuration: `source ~/.zshrc`

### Functions/Aliases Not Working
Modern shell tools (zoxide, starship, custom functions) may not work.
Workarounds:
- Use basic commands instead of aliases
- Use absolute paths instead of relative navigation
- Manually define functions in Claude Code session
'''
        
        config_file.write_text(content)
    
    def _update_claude_md(self, project_root: Path):
        """Update or create CLAUDE.md with shell configuration instructions."""
        claude_md = project_root / "CLAUDE.md"
        
        shell_config_section = '''
## Shell Configuration

Claude Code has limitations with shell configuration loading. To work around this:

1. **For commands needing shell environment**:
   ```bash
   source .claude/shell-helper.sh && your_command
   ```

2. **For one-off commands with shell config**:
   ```bash
   zsh -c 'source ~/.zshrc && your_command'
   ```

3. **Always use absolute paths** when possible to avoid PATH issues

4. **Quote paths with spaces** to prevent command parsing errors

5. **Set environment variables** in `.claude/settings.json` rather than shell config

See `.claude/shell-config.md` for detailed troubleshooting.

'''
        
        if claude_md.exists():
            content = claude_md.read_text()
            if "## Shell Configuration" not in content:
                # Append to existing CLAUDE.md
                claude_md.write_text(content + shell_config_section)
        else:
            # Create new CLAUDE.md
            header = f'''# {project_root.name}

This project uses kaia-guardrails hooks for development workflow automation.
'''
            claude_md.write_text(header + shell_config_section)


# Hook instance for the orchestrator
shell_config_hook = ClaudeShellConfigHook(
    name="claude-shell-config",
    priority=10,  # Run early in the hook sequence
    enabled=True
)

if __name__ == "__main__":
    # Can be run standalone for testing
    hook = ClaudeShellConfigHook()
    result = hook.run({})
    print(f"Hook result: {result}")
