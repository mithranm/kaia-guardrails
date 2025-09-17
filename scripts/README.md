# Kaia Guardrails Shell Integration Scripts

These scripts provide clean installation and removal of the Kaia Guardrails shell command interceptor system.

## Training Data Location

**All training data is saved to: `~/.kaia/analytics/`**

The main file is:
- `~/.kaia/analytics/commands.jsonl` - JSON Lines format with command analysis data
- `~/.kaia/analytics/sessions.jsonl` - Session tracking data
- `~/.kaia/analytics/collector.log` - System logs

## Installation

Run the installer to set up shell integration:

```bash
cd ~/GitHub/killeraiagent/tools/kaia-guardrails
python3 scripts/install_shell_integration.py
```

This will:
- Create `~/.shell_interceptor/` directory with command wrappers
- Set up the main interceptor script that uses kaia-guardrails
- Add shell integration to your profile (`.zshrc`, `.bash_profile`, etc.)
- Create the analytics data directory structure

After installation:
- Restart your terminal or run `source ~/.zshrc`
- Use `kaia-status` to check if the system is active
- Use `kaia-data` to see where training data is stored
- Use `kaia-off` to temporarily disable (for testing)
- Use `kaia-on` to re-enable

## Uninstallation  

Run the uninstaller to cleanly remove all components:

```bash
cd ~/GitHub/killeraiagent/tools/kaia-guardrails
python3 scripts/uninstall_shell_integration.py
```

This will:
- Remove all interceptor scripts from `~/.shell_interceptor/`
- Clean up shell profile modifications
- Ask if you want to preserve training data in `~/.kaia/analytics/`
- Disable the interceptor in your current session

## Manual Commands

If you need to manually control the system:

```bash
# Check status
kaia-status

# Enable interceptor
kaia-on

# Disable interceptor  
kaia-off

# View training data location
kaia-data

# View current training data
ls -la ~/.kaia/analytics/
head ~/.kaia/analytics/commands.jsonl
```

## Integration with Package Managers

For pip/conda installation, you can call these scripts from your package's post-install hooks:

```python
# In setup.py or similar
import subprocess
import sys
from pathlib import Path

def post_install():
    script_path = Path(__file__).parent / "scripts" / "install_shell_integration.py"
    subprocess.run([sys.executable, str(script_path)])

def pre_uninstall():
    script_path = Path(__file__).parent / "scripts" / "uninstall_shell_integration.py" 
    subprocess.run([sys.executable, str(script_path)])
```

## Files Created

**Interceptor Directory**: `~/.shell_interceptor/`
- `kaia_interceptor.py` - Main interceptor script
- `shell_integration.sh` - Shell functions and aliases
- Individual command wrappers: `rm`, `cp`, `mv`, etc.

**Data Directory**: `~/.kaia/`
- `analytics/commands.jsonl` - Training data
- `analytics/sessions.jsonl` - Session tracking  
- `analytics/collector.log` - System logs
- `config/` - Configuration files

**Shell Profile Modifications**:
- Adds source line to `.zshrc`, `.bash_profile`, etc.
- Adds marker comments for clean removal
