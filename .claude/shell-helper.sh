#!/bin/zsh
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
