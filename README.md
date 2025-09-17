# Kaia Guardrails

Core command execution analytics and guardrails system for kaia AI agents.

## Overview

Kaia Guardrails is a permanent, always-on analytics collection system that:

- **Analyzes every command** before execution with rich feature extraction
- **Collects training data** for local classifier development
- **Provides LLM-based risk assessment** with human oversight
- **Ensures compliance** with project rules (vibelint, CLAUDE.md, etc.)
- **Maintains complete audit trail** of all command decisions

## Features

- 🔍 **Rich Command Analysis**: 25+ features extracted per command
- 🤖 **LLM Integration**: Uses your local LLM for intelligent risk assessment
- 👤 **Human Oversight**: Interactive approval for medium/high-risk operations
- 📊 **Analytics Collection**: Structured data for training local classifiers
- ✅ **Project Compliance**: Integrates with vibelint and project rules
- 🚀 **Performance Optimized**: Fast local decisions for common operations
- 🔒 **Security Focused**: Prevents dangerous operations while maintaining productivity

## Installation

```bash
# Clone and install
git clone <repo-url> ~/GitHub/kaia-guardrails
cd ~/GitHub/kaia-guardrails
pip install -e .

# Install shell integration
kaia-guardrails install

# Restart shell
source ~/.zshrc
```

## Usage

Once installed, the system runs automatically and transparently:

- **Low-risk commands** (like `ls`, `git status`) execute immediately
- **Medium-risk commands** get LLM analysis with optional human review  
- **High-risk commands** require explicit approval
- **All commands** are logged with rich analytics for ML training

### Management Commands

```bash
# Check system status
kaia-guardrails status

# View analytics
kaia-guardrails analyze

# Export training data
kaia-guardrails export

# Create dashboard
kaia-guardrails dashboard
```

## Configuration

The system uses these configuration files:

- `~/.kaia/config.json` - Main configuration
- `~/.kaia/analytics/` - Analytics data storage
- `~/.kaia/rules/` - Custom project rules

## Architecture

```
kaia-guardrails/
├── src/kaia_guardrails/
│   ├── __init__.py
│   ├── analytics.py          # Core analytics collection
│   ├── interceptor.py         # Command interception
│   ├── classifier.py          # Risk assessment
│   ├── llm_client.py          # LLM integration
│   └── shell_integration.py   # Shell wrapper management
├── tests/
├── pyproject.toml
└── README.md
```

## Integration

The system integrates seamlessly with:

- **Claude Code**: Automatic activation when Claude Code is running
- **vibelint**: Python code compliance checking
- **Project Rules**: CLAUDE.md and AGENTS.instructions.md compliance
- **Git Workflows**: Safe git operations with audit trails

## Analytics Data

All command executions generate rich analytics including:

- Command structure and arguments
- File system impact analysis  
- Risk assessment scores
- LLM decision reasoning
- Human override patterns
- Execution timing and results
- Project compliance status

This data enables training of highly accurate local classifiers tailored to your specific development patterns.

## Privacy & Security

- **Local-first**: All analytics stored locally in `~/.kaia/`
- **No external transmission**: Data never leaves your machine
- **Configurable**: Full control over what gets logged
- **Transparent**: Complete audit trail of all decisions
