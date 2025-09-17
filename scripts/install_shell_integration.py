#!/usr/bin/env python3
"""
Kaia Guardrails Shell Integration Installer

This script sets up shell command interception for the kaia-guardrails system.
It creates interceptor scripts and modifies shell profiles for seamless integration.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

class KaiaInstaller:
    """Install kaia-guardrails shell integration"""
    
    def __init__(self):
        self.home = Path.home()
        self.interceptor_dir = self.home / ".shell_interceptor" 
        self.kaia_dir = self.home / ".kaia"
        self.current_dir = Path(__file__).parent.parent
        
        # Commands to intercept for analysis
        self.commands_to_intercept = [
            'rm', 'rmdir', 'mv', 'cp', 'chmod', 'chown', 'ln', 'unlink',
            'touch', 'mkdir', 'tar', 'zip', 'unzip', 'gunzip', 'gzip',
            'rsync', 'scp', 'sftp', 'dd', 'sudo', 'nano', 'vi', 'vim', 
            'ed', 'cat', 'echo', 'tee', 'sed', 'awk'
        ]        
    def create_directories(self):
        """Create necessary directories"""
        print("📁 Creating directories...")
        
        directories = [
            self.interceptor_dir,
            self.interceptor_dir / "original_commands",
            self.kaia_dir / "analytics",
            self.kaia_dir / "config",
            self.kaia_dir / "logs"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ {directory}")
    
    def create_main_interceptor(self):
        """Create the main interceptor script"""
        print("🐍 Creating main interceptor script...")
        
        interceptor_script = f'''#!/usr/bin/env python3
"""
Kaia Command Interceptor - Bridge to kaia-guardrails system
"""

import sys
import os
import subprocess
from pathlib import Path

# Add the kaia-guardrails src directory to Python path
KAIA_GUARDRAILS_DIR = Path("{self.current_dir}/src")
sys.path.insert(0, str(KAIA_GUARDRAILS_DIR))

# Check if interceptor is disabled
if os.environ.get('SHELL_INTERCEPTOR_ACTIVE') != '1':
    if len(sys.argv) >= 2:
        command = sys.argv[1]
        args = sys.argv[2:]
        
        # Find and execute original command
        try:
            result = subprocess.run(['which', '-a', command], capture_output=True, text=True)
            paths = result.stdout.strip().split('\\n')
            interceptor_path = os.path.expanduser('~/.shell_interceptor')
            original_paths = [p for p in paths if not p.startswith(interceptor_path)]
            
            if original_paths:
                original_cmd = original_paths[0]
            else:
                # Fallback to common system paths
                for path in ['/bin', '/usr/bin', '/usr/local/bin']:
                    cmd_path = os.path.join(path, command)
                    if os.path.exists(cmd_path):
                        original_cmd = cmd_path
                        break
                else:
                    original_cmd = command
            
            result = subprocess.run([original_cmd] + args)
            sys.exit(result.returncode)
        except Exception:
            sys.exit(1)
    sys.exit(1)

# Try to import kaia-guardrails
try:
    from kaia_guardrails.interceptor import CommandInterceptor
except ImportError as e:
    print(f"Warning: kaia-guardrails not available: {{e}}", file=sys.stderr)
    print("Executing command directly without guardrails...", file=sys.stderr)
    
    if len(sys.argv) >= 2:
        command = sys.argv[1]
        args = sys.argv[2:]
        try:
            result = subprocess.run(['which', command], capture_output=True, text=True)
            if result.returncode == 0:
                original_cmd = result.stdout.strip().split('\\n')[0]
                result = subprocess.run([original_cmd] + args)
                sys.exit(result.returncode)
        except Exception:
            pass
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: kaia_interceptor.py <command> [args...]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]
    args = sys.argv[2:]
    
    try:
        # Initialize the kaia-guardrails interceptor
        interceptor = CommandInterceptor()
        
        # Process the command through kaia-guardrails
        should_execute = interceptor.intercept_command(command, args)
        
        if should_execute:
            # Find original command path
            try:
                result = subprocess.run(['which', '-a', command], capture_output=True, text=True)
                paths = result.stdout.strip().split('\\n')
                interceptor_path = os.path.expanduser('~/.shell_interceptor')
                original_paths = [p for p in paths if not p.startswith(interceptor_path)]
                
                if original_paths:
                    original_cmd = original_paths[0]
                else:
                    original_cmd = command
                
                # Execute the original command
                result = subprocess.run([original_cmd] + args)
                sys.exit(result.returncode)
                
            except Exception as e:
                print(f"Error executing {{command}}: {{e}}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Command '{{command}}' was blocked by kaia-guardrails", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"Error in kaia interceptor: {{e}}", file=sys.stderr)
        
        # Fallback: execute directly
        try:
            result = subprocess.run([command] + args)
            sys.exit(result.returncode)
        except Exception:
            sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        interceptor_path = self.interceptor_dir / "kaia_interceptor.py"
        interceptor_path.write_text(interceptor_script)
        interceptor_path.chmod(0o755)
        print(f"   ✅ {interceptor_path}")
    
    def create_command_wrappers(self):
        """Create wrapper scripts for each intercepted command"""
        print("📝 Creating command wrapper scripts...")
        
        for command in self.commands_to_intercept:
            wrapper_script = f'''#!/bin/bash
# Kaia guardrails wrapper for {command}
exec python3 "$HOME/.shell_interceptor/kaia_interceptor.py" "{command}" "$@"
'''
            wrapper_path = self.interceptor_dir / command
            wrapper_path.write_text(wrapper_script)
            wrapper_path.chmod(0o755)
            print(f"   ✅ {command}")
    
    def create_shell_integration(self):
        """Create shell integration script"""
        print("🐚 Creating shell integration script...")
        
        integration_script = '''# Shell Command Interceptor Integration
# Kaia Guardrails - Command Analysis and Safety

# Function to activate interception
kaia_activate() {
    if [[ "$SHELL_INTERCEPTOR_ACTIVE" == "1" ]]; then
        return 0
    fi
    
    export SHELL_INTERCEPTOR_ACTIVE=1
    export PATH="$HOME/.shell_interceptor:$PATH"
    
    echo "🛡️  Kaia guardrails activated - analyzing commands for safety"
}

# Function to deactivate interception
kaia_deactivate() {
    if [[ "$SHELL_INTERCEPTOR_ACTIVE" != "1" ]]; then
        return 0
    fi
    
    export PATH="${PATH//$HOME\\.shell_interceptor:/}"
    unset SHELL_INTERCEPTOR_ACTIVE
    
    echo "🔓 Kaia guardrails deactivated - commands execute directly"
}

# Function to check status
kaia_status() {
    if [[ "$SHELL_INTERCEPTOR_ACTIVE" == "1" ]]; then
        echo "🛡️  Kaia guardrails: ACTIVE"
    else
        echo "🔓 Kaia guardrails: INACTIVE"
    fi
    echo "Training data location: ~/.kaia/analytics/"
}

# Activate by default
kaia_activate

# Convenient aliases
alias kaia-on="kaia_activate"
alias kaia-off="kaia_deactivate" 
alias kaia-status="kaia_status"
alias kaia-data="echo 'Training data: ~/.kaia/analytics/commands.jsonl'"
'''
        
        integration_path = self.interceptor_dir / "shell_integration.sh"
        integration_path.write_text(integration_script)
        print(f"   ✅ {integration_path}")
        
        return integration_path
    
    def update_shell_profile(self, integration_path: Path):
        """Update shell profile to source the integration script"""
        print("🔧 Updating shell profiles...")
        
        # Detect shell and profile files
        profiles_to_check = [
            self.home / ".zshrc",
            self.home / ".bash_profile", 
            self.home / ".bashrc",
            self.home / ".profile"
        ]
        
        source_line = f"source {integration_path}"
        marker_comment = "# Kaia Guardrails Integration"
        
        profiles_updated = []
        
        for profile_path in profiles_to_check:
            if profile_path.exists():
                content = profile_path.read_text()
                
                # Check if already integrated
                if marker_comment in content:
                    print(f"   ⚠️  Already integrated in {profile_path}")
                    continue
                
                # Add integration
                with profile_path.open('a') as f:
                    f.write(f"\\n{marker_comment}\\n")
                    f.write(f"{source_line}\\n")
                
                profiles_updated.append(profile_path)
                print(f"   ✅ Updated {profile_path}")
        
        if not profiles_updated:
            print("   ⚠️  No shell profiles found or all already configured")
        
        return profiles_updated
    
    def install(self):
        """Run the complete installation"""
        print("🚀 Installing Kaia Guardrails Shell Integration\\n")
        
        try:
            self.create_directories()
            self.create_main_interceptor()
            self.create_command_wrappers()
            integration_path = self.create_shell_integration()
            profiles_updated = self.update_shell_profile(integration_path)
            
            print("\\n✅ Installation completed successfully!\\n")
            
            print("📋 Next steps:")
            print("   1. Restart your terminal or run: source ~/.zshrc")
            print("   2. Training data will be saved to: ~/.kaia/analytics/")
            print("   3. Use 'kaia-status' to check if the system is active")
            print("   4. Use 'kaia-off' to temporarily disable")
            print("   5. Use 'kaia-data' to see training data location\\n")
            
            if profiles_updated:
                print("🔄 Shell profiles updated. Please restart your terminal!")
            
        except Exception as e:
            print(f"❌ Installation failed: {e}")
            sys.exit(1)

def main():
    installer = KaiaInstaller()
    installer.install()

if __name__ == "__main__":
    main()
