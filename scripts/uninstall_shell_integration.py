#!/usr/bin/env python3
"""
Kaia Guardrails Shell Integration Uninstaller

This script removes shell command interception for the kaia-guardrails system.
It removes interceptor scripts and cleans up shell profile modifications.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

class KaiaUninstaller:
    """Uninstall kaia-guardrails shell integration"""
    
    def __init__(self):
        self.home = Path.home()
        self.interceptor_dir = self.home / ".shell_interceptor" 
        self.kaia_dir = self.home / ".kaia"
        
    def remove_interceptor_scripts(self):
        """Remove all interceptor scripts"""
        print("🗑️  Removing interceptor scripts...")
        
        if self.interceptor_dir.exists():
            try:
                shutil.rmtree(self.interceptor_dir)
                print(f"   ✅ Removed {self.interceptor_dir}")
            except Exception as e:
                print(f"   ❌ Failed to remove {self.interceptor_dir}: {e}")
        else:
            print(f"   ⚠️  Directory {self.interceptor_dir} not found")
    
    def clean_shell_profiles(self):
        """Remove kaia integration from shell profiles"""
        print("🧹 Cleaning shell profiles...")
        
        profiles_to_check = [
            self.home / ".zshrc",
            self.home / ".bash_profile", 
            self.home / ".bashrc",
            self.home / ".profile"
        ]
        
        marker_comment = "# Kaia Guardrails Integration"
        profiles_cleaned = []
        
        for profile_path in profiles_to_check:
            if not profile_path.exists():
                continue
                
            try:
                content = profile_path.read_text()
                
                # Check if integration exists
                if marker_comment not in content:
                    continue
                
                # Remove integration section
                lines = content.split('\\n')
                cleaned_lines = []
                skip_section = False
                
                for line in lines:
                    if marker_comment in line:
                        skip_section = True
                        continue
                    elif skip_section and line.strip() == "":
                        # End of section
                        skip_section = False
                        continue
                    elif skip_section and line.startswith("source") and "shell_integration.sh" in line:
                        # Skip the source line
                        skip_section = False
                        continue
                    elif not skip_section:
                        cleaned_lines.append(line)
                
                # Write cleaned content back
                profile_path.write_text('\\n'.join(cleaned_lines))
                profiles_cleaned.append(profile_path)
                print(f"   ✅ Cleaned {profile_path}")
                
            except Exception as e:
                print(f"   ❌ Failed to clean {profile_path}: {e}")
        
        if not profiles_cleaned:
            print("   ⚠️  No shell profiles needed cleaning")
        
        return profiles_cleaned
    
    def preserve_training_data(self):
        """Ask user if they want to keep training data"""
        print("📊 Training data handling...")
        
        analytics_dir = self.kaia_dir / "analytics"
        if not analytics_dir.exists():
            print("   ⚠️  No training data found")
            return False
        
        print(f"   📁 Training data found in: {analytics_dir}")
        
        # Count data files
        data_files = list(analytics_dir.glob("*.jsonl")) + list(analytics_dir.glob("*.json"))
        if data_files:
            print(f"   📈 Found {len(data_files)} data files")
            for data_file in data_files[:5]:  # Show first 5
                size = data_file.stat().st_size
                print(f"      - {data_file.name} ({size} bytes)")
            if len(data_files) > 5:
                print(f"      ... and {len(data_files) - 5} more files")
        
        # Ask user
        response = input("\\n   Keep training data? (y/N): ").strip().lower()
        
        if response in ['y', 'yes']:
            print("   ✅ Training data preserved")
            return True
        else:
            try:
                shutil.rmtree(analytics_dir)
                print("   🗑️  Training data removed")
                
                # Remove parent .kaia directory if it's empty
                if self.kaia_dir.exists() and not list(self.kaia_dir.iterdir()):
                    self.kaia_dir.rmdir()
                    print(f"   🗑️  Removed empty {self.kaia_dir}")
                    
                return False
            except Exception as e:
                print(f"   ❌ Failed to remove training data: {e}")
                return True
    
    def disable_current_session(self):
        """Disable interceptor in current session"""
        print("🔓 Disabling interceptor in current session...")
        
        try:
            # Remove from current PATH if present
            current_path = os.environ.get('PATH', '')
            interceptor_path = str(self.interceptor_dir)
            
            if interceptor_path in current_path:
                new_path = current_path.replace(f"{interceptor_path}:", "")
                new_path = new_path.replace(f":{interceptor_path}", "")
                os.environ['PATH'] = new_path
                print("   ✅ Removed from current PATH")
            
            # Unset environment variable
            if 'SHELL_INTERCEPTOR_ACTIVE' in os.environ:
                del os.environ['SHELL_INTERCEPTOR_ACTIVE']
                print("   ✅ Unset SHELL_INTERCEPTOR_ACTIVE")
                
        except Exception as e:
            print(f"   ⚠️  Could not modify current session: {e}")
    
    def uninstall(self):
        """Run the complete uninstallation"""
        print("🚀 Uninstalling Kaia Guardrails Shell Integration\\n")
        
        try:
            self.disable_current_session()
            self.remove_interceptor_scripts()
            profiles_cleaned = self.clean_shell_profiles()
            data_preserved = self.preserve_training_data()
            
            print("\\n✅ Uninstallation completed successfully!\\n")
            
            print("📋 Summary:")
            print("   • Interceptor scripts removed")
            if profiles_cleaned:
                print(f"   • {len(profiles_cleaned)} shell profiles cleaned")
            if data_preserved:
                print("   • Training data preserved in ~/.kaia/analytics/")
            else:
                print("   • Training data removed")
            
            print("\\n🔄 Please restart your terminal to complete removal!")
            
        except Exception as e:
            print(f"❌ Uninstallation failed: {e}")
            sys.exit(1)

def main():
    print("⚠️  This will remove Kaia Guardrails shell integration")
    response = input("Continue? (y/N): ").strip().lower()
    
    if response not in ['y', 'yes']:
        print("Uninstallation cancelled")
        sys.exit(0)
    
    uninstaller = KaiaUninstaller()
    uninstaller.uninstall()

if __name__ == "__main__":
    main()
