# Shell Configuration for Claude Code

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
