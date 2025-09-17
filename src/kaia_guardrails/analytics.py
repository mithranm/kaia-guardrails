"""
Core analytics collection system for command execution
"""
import os
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging
import subprocess

@dataclass
class CommandAnalytics:
    """Complete command analytics record"""
    
    # Command identification
    command: str
    args: List[str]
    full_command: str
    command_hash: str
    
    # Context
    cwd: str
    user: str
    session_id: str
    timestamp: float
    parent_process: str
    
    # Environment detection
    is_git_repo: bool
    is_python_project: bool
    is_kaia_session: bool
    claude_code_active: bool
    
    # File system analysis
    targets_existing_files: bool
    targets_system_paths: bool
    creates_new_files: bool
    modifies_permissions: bool
    file_count_affected: int
    
    # Risk assessment
    risk_score: float
    is_destructive: bool
    uses_sudo: bool
    has_wildcards: bool
    affects_multiple_files: bool
    
    # Decision tracking
    llm_decision: Optional[str] = None
    llm_confidence: Optional[float] = None
    llm_reasoning: Optional[str] = None
    llm_response_time_ms: Optional[float] = None
    
    human_decision: Optional[str] = None
    human_response_time_ms: Optional[float] = None
    
    final_decision: str = "pending"
    decision_authority: str = "pending"  # llm|human|auto
    
    # Performance tracking
    execution_time_ms: Optional[float] = None
    exit_code: Optional[int] = None
    
    # Compliance
    vibelint_compliant: Optional[bool] = None
    project_rules_compliant: Optional[bool] = None

class KaiaAnalyticsCollector:
    """Core analytics collection system - always running"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.setup_directories()
        self.setup_logging()
        self.session_id = self.generate_session_id()
        
    def setup_directories(self):
        """Setup analytics directories"""
        self.kaia_dir = Path.home() / ".kaia"
        self.analytics_dir = self.kaia_dir / "analytics"
        self.config_dir = self.kaia_dir / "config"
        
        for directory in [self.kaia_dir, self.analytics_dir, self.config_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.commands_file = self.analytics_dir / "commands.jsonl"
        self.sessions_file = self.analytics_dir / "sessions.jsonl"
        self.daily_summary_file = self.analytics_dir / f"daily_{time.strftime('%Y%m%d')}.json"
        
    def setup_logging(self):
        """Setup logging system"""
        log_file = self.analytics_dir / "collector.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler() if self.config.get("debug") else logging.NullHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def generate_session_id(self) -> str:
        """Generate unique session identifier"""
        session_data = f"{os.environ.get('USER')}_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        return hashlib.md5(session_data.encode()).hexdigest()[:12]
    
    def analyze_command(self, command: str, args: List[str], cwd: str) -> CommandAnalytics:
        """Analyze command and create analytics record"""
        full_command = f"{command} {' '.join(args)}"
        
        analytics = CommandAnalytics(
            # Basic info
            command=command,
            args=args,
            full_command=full_command,
            command_hash=hashlib.md5(full_command.encode()).hexdigest()[:8],
            cwd=cwd,
            user=os.environ.get("USER", "unknown"),
            session_id=self.session_id,
            timestamp=time.time(),
            parent_process=self._get_parent_process(),
            
            # Environment
            is_git_repo=(Path(cwd) / ".git").exists(),
            is_python_project=self._is_python_project(cwd),
            is_kaia_session=self._detect_kaia_session(),
            claude_code_active="CLAUDE_CODE_ACTIVE" in os.environ,
            
            # File system analysis
            targets_existing_files=self._targets_existing_files(args, cwd),
            targets_system_paths=self._targets_system_paths(args),
            creates_new_files=self._creates_new_files(command, args),
            modifies_permissions=command in ["chmod", "chown", "chgrp"],
            file_count_affected=self._count_affected_files(args, cwd),
            
            # Risk assessment
            risk_score=self._calculate_risk_score(command, args),
            is_destructive=self._is_destructive(command, args),
            uses_sudo=command == "sudo" or "sudo" in args,
            has_wildcards=any("*" in arg or "?" in arg for arg in args),
            affects_multiple_files=self._affects_multiple_files(args),
            
            # Compliance
            vibelint_compliant=self._check_vibelint_compliance(args),
            project_rules_compliant=self._check_project_rules(full_command)
        )
        
        return analytics
    
    def record_analytics(self, analytics: CommandAnalytics) -> None:
        """Store analytics record"""
        with open(self.commands_file, 'a') as f:
            f.write(json.dumps(asdict(analytics), default=str) + '\n')
        
        self.logger.info(
            f"ANALYTICS: {analytics.command_hash} - {analytics.full_command} "
            f"-> {analytics.final_decision} (risk: {analytics.risk_score:.3f})"
        )
    
    def update_execution_result(self, command_hash: str, execution_time: float, exit_code: int):
        """Update analytics with execution results"""
        self.logger.info(
            f"EXEC_RESULT: {command_hash} - time:{execution_time:.2f}ms exit:{exit_code}"
        )
        # In production, would update the record in place
        
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get analytics summary"""
        if not self.commands_file.exists():
            return {"total_commands": 0, "message": "No analytics data yet"}
        
        try:
            with open(self.commands_file, 'r') as f:
                records = [json.loads(line) for line in f if line.strip()]
            
            if not records:
                return {"total_commands": 0, "message": "No analytics data yet"}
            
            # Calculate summary statistics
            total = len(records)
            decisions = [r.get("final_decision", "unknown") for r in records]
            authorities = [r.get("decision_authority", "unknown") for r in records]
            risks = [r.get("risk_score", 0) for r in records if isinstance(r.get("risk_score"), (int, float))]
            
            from collections import Counter
            
            return {
                "total_commands": total,
                "decisions": dict(Counter(decisions)),
                "authorities": dict(Counter(authorities)),
                "avg_risk_score": sum(risks) / len(risks) if risks else 0.0,
                "last_updated": max(r.get("timestamp", 0) for r in records) if records else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting analytics summary: {e}")
            return {"error": str(e)}
    
    # Helper methods
    def _get_parent_process(self) -> str:
        """Get parent process name"""
        try:
            ppid = os.getppid()
            result = subprocess.run(
                ['ps', '-p', str(ppid), '-o', 'comm='], 
                capture_output=True, text=True, timeout=1
            )
            return result.stdout.strip()
        except:
            return "unknown"
    
    def _is_python_project(self, cwd: str) -> bool:
        """Check if current directory is a Python project"""
        python_files = ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"]
        return any((Path(cwd) / f).exists() for f in python_files)
    
    def _detect_kaia_session(self) -> bool:
        """Detect if we're in a kaia/Claude Code session"""
        indicators = [
            "KAIA_ACTIVE" in os.environ,
            "CLAUDE_CODE_ACTIVE" in os.environ,
            any("kaia" in str(v).lower() for v in os.environ.values()),
        ]
        return any(indicators)
    
    def _targets_existing_files(self, args: List[str], cwd: str) -> bool:
        """Check if command targets existing files"""
        for arg in args:
            if not arg.startswith('-') and (Path(cwd) / arg).exists():
                return True
        return False
    
    def _targets_system_paths(self, args: List[str]) -> bool:
        """Check if command targets system paths"""
        system_paths = ['/etc/', '/usr/bin/', '/sbin/', '/Library/', '/System/']
        return any(any(path in arg for path in system_paths) for arg in args)
    
    def _creates_new_files(self, command: str, args: List[str]) -> bool:
        """Check if command creates new files"""
        creation_commands = ['touch', 'mkdir', 'cp', 'mv']
        if command in creation_commands:
            return True
        return any('>' in arg for arg in args)
    
    def _count_affected_files(self, args: List[str], cwd: str) -> int:
        """Estimate number of files affected"""
        count = 0
        for arg in args:
            if not arg.startswith('-'):
                if '*' in arg or '?' in arg:
                    count += 5  # Estimate for wildcards
                elif (Path(cwd) / arg).exists():
                    count += 1
        return count
    
    def _calculate_risk_score(self, command: str, args: List[str]) -> float:
        """Calculate risk score 0.0 to 1.0"""
        score = 0.0
        
        # Base command risk
        high_risk = ['rm', 'dd', 'mkfs', 'fdisk', 'sudo', 'kill']
        medium_risk = ['chmod', 'chown', 'mv', 'cp', 'ln']
        
        if command in high_risk:
            score += 0.4
        elif command in medium_risk:
            score += 0.2
        
        # Dangerous flags
        dangerous_flags = ['-rf', '--force', '-f', '--delete', '--recursive']
        if any(flag in ' '.join(args) for flag in dangerous_flags):
            score += 0.3
        
        # System paths
        if self._targets_system_paths(args):
            score += 0.2
        
        # Wildcards
        if any('*' in arg for arg in args):
            score += 0.1
        
        return min(score, 1.0)
    
    def _is_destructive(self, command: str, args: List[str]) -> bool:
        """Check if command is destructive"""
        destructive_commands = ['rm', 'rmdir', 'dd', 'mkfs', 'fdisk']
        if command in destructive_commands:
            return True
        
        destructive_patterns = ['-rf', '--force', '--delete']
        return any(pattern in ' '.join(args) for pattern in destructive_patterns)
    
    def _affects_multiple_files(self, args: List[str]) -> bool:
        """Check if command affects multiple files"""
        if any(flag in args for flag in ['-r', '-R', '--recursive']):
            return True
        if any('*' in arg for arg in args):
            return True
        non_flag_args = [arg for arg in args if not arg.startswith('-')]
        return len(non_flag_args) > 2
    
    def _check_vibelint_compliance(self, args: List[str]) -> Optional[bool]:
        """Check vibelint compliance for Python files"""
        # Look for vibelint in known locations
        possible_paths = [
            Path.home() / "GitHub/killeraiagent/tools/vibelint",
            Path("vibelint"),  # Current directory
        ]
        
        vibelint_path = None
        for path in possible_paths:
            if path.exists():
                vibelint_path = path
                break
        
        if not vibelint_path:
            return None
        
        python_files = [arg for arg in args if arg.endswith('.py') and Path(arg).exists()]
        if not python_files:
            return None
        
        try:
            for py_file in python_files:
                result = subprocess.run([
                    "python3", "-c",
                    f"import sys; sys.path.append('{vibelint_path}/src'); "
                    "from vibelint.cli import main; "
                    f"sys.argv = ['vibelint', 'check', '{py_file}']; "
                    "main()"
                ], capture_output=True, text=True, timeout=3, cwd=str(vibelint_path))
                
                if result.returncode != 0:
                    return False
            return True
        except:
            return None
    
    def _check_project_rules(self, command: str) -> Optional[bool]:
        """Check compliance with project rules"""
        rules_files = [
            Path.home() / "GitHub/killeraiagent/CLAUDE.md",
            Path("CLAUDE.md"),
            Path("README.md"),
        ]
        
        for rules_file in rules_files:
            if rules_file.exists():
                try:
                    rules = rules_file.read_text().lower()
                    command_lower = command.lower()
                    
                    # Basic rule checking
                    if 'miniconda environment' in rules and 'pip install' in command_lower:
                        if 'conda' not in command_lower:
                            return False
                    
                    return True
                except:
                    continue
        
        return None  # No rules found
