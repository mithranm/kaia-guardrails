# Kaia Guardrails - Security & Analytics Instructions

## Purpose
Command execution security and analytics system for AI agents. Provides LLM-based approval, risk assessment, and comprehensive audit trails for safe AI-assisted development.

## Parent Project Context
- **Main Project**: Follow `/AGENTS.instructions.md` for overall Kaia project standards
- **Role**: Security-focused development with emphasis on reliability and performance
- **Integration**: Operates as submodule within larger AI agent projects

## Architecture Overview
- **Analytics Engine**: `src/kaia_guardrails/analytics.py` - Rich command feature extraction
- **Risk Classifier**: `src/kaia_guardrails/classifier.py` - Fast local risk assessment  
- **Command Interceptor**: `src/kaia_guardrails/interceptor.py` - OS-level command capturing
- **LLM Integration**: `src/kaia_guardrails/llm_client.py` - Intelligent approval decisions
- **CLI Tools**: Management interface and analytics dashboard

## Development Commands
- `pip install -e .` - Install in development mode
- `kaia-guardrails install` - Install shell integration
- `kaia-guardrails status` - Check system status and health
- `kaia-guardrails analyze` - View analytics dashboard
- `kaia-guardrails export` - Export training data
- `pytest` - Run comprehensive test suite

## Critical Security Requirements
- **Local-only operation** - All data stays on user's machine, never transmitted
- **Fail-safe design** - Default to denial when uncertain about command safety  
- **Complete audit trail** - Log every decision with reasoning and context
- **Performance critical** - <1ms response for common command classifications
- **User control** - Respect user approval/denial decisions and learn from them

## Code Standards
- Follow main project code style (88 char limit, type hints, PEP 8)
- **Extra emphasis on error handling** - security code must be bulletproof
- **Comprehensive logging** - every decision path must be traceable
- **Documentation critical** - all security logic must be clearly documented
- **Test everything** - security decisions need thorough test coverage

## Integration Requirements
- **Never bypass parent project security** - respect existing guardrails
- **Follow vibelint compliance** when integrated with vibelint-enabled projects
- **Configurable thresholds** - adapt to different project risk tolerances
- **Framework agnostic** - works with Claude Code, Cursor, or any AI coding tool

## Data Collection & Privacy
- Collect rich analytics (25+ features per command) for ML training
- Store locally in `~/.kaia/analytics/` - never sync or transmit
- Respect user privacy - no personal data in collected features
- Enable/disable collection via configuration
- Provide clear data export and deletion capabilities

## Development Focus Areas
- **Performance optimization** - minimize latency for developer productivity
- **Accuracy improvement** - reduce false positives/negatives in risk assessment
- **Feature engineering** - develop better command analysis capabilities
- **Integration testing** - ensure compatibility with various development environments
- **Documentation** - maintain clear setup and usage instructions

## Submodule Development Notes
- Changes here should be committed to the kaia-guardrails repository first
- Test integration with parent project after major changes
- Coordinate releases with parent project maintainers
- Follow semantic versioning for independent releases
- Document any breaking changes that affect parent project integration