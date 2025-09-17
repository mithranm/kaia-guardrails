"""
Risk classifier for command assessment
"""
import re
from typing import List

from .analytics import CommandAnalytics

class RiskClassifier:
    """Local risk classifier for commands"""
    
    def __init__(self):
        # Patterns for auto-approval (very safe commands)
        self.auto_approve_patterns = [
            r'^git status$',
            r'^git log',
            r'^git diff',
            r'^ls\s',
            r'^cat\s',
            r'^head\s',
            r'^tail\s',
            r'^grep\s',
            r'^find\s.*-name',
            r'^python3?\s.*test',
            r'^pytest\s',
            r'^cd\s',
            r'^pwd$',
            r'^echo\s',
            r'^which\s',
            r'^man\s',
            r'^help\s'
        ]
        
        # Patterns for auto-denial (very dangerous commands)
        self.auto_deny_patterns = [
            r'sudo.*rm.*-rf.*/',
            r'rm.*-rf.*/',
            r'chmod.*777',
            r'.*>/etc/passwd',
            r'.*>/etc/shadow',
            r'dd.*if=.*of=/dev/',
            r'mkfs\.',
            r'fdisk.*',
            r'kill.*-9.*'
        ]
    
    def classify(self, analytics: CommandAnalytics) -> str:
        """Classify command as approve/deny/review"""
        
        full_command = analytics.full_command
        
        # Check auto-approve patterns
        for pattern in self.auto_approve_patterns:
            if re.search(pattern, full_command, re.IGNORECASE):
                return "approve"
        
        # Check auto-deny patterns
        for pattern in self.auto_deny_patterns:
            if re.search(pattern, full_command, re.IGNORECASE):
                return "deny"
        
        # Risk-based decision
        if analytics.risk_score >= 0.7:
            return "deny"
        elif analytics.risk_score >= 0.4:
            return "review"  # Needs human/LLM review
        else:
            return "approve"
    
    def get_risk_factors(self, analytics: CommandAnalytics) -> List[str]:
        """Get list of risk factors for explanation"""
        factors = []
        
        if analytics.is_destructive:
            factors.append("destructive operation")
        if analytics.uses_sudo:
            factors.append("requires elevated privileges")
        if analytics.targets_system_paths:
            factors.append("modifies system files")
        if analytics.affects_multiple_files:
            factors.append("affects multiple files")
        if analytics.has_wildcards:
            factors.append("uses wildcards")
        if analytics.modifies_permissions:
            factors.append("changes file permissions")
        if analytics.vibelint_compliant is False:
            factors.append("code quality violations")
        if analytics.project_rules_compliant is False:
            factors.append("project rule violations")
        
        return factors
    
    def explain_decision(self, analytics: CommandAnalytics, decision: str) -> str:
        """Provide explanation for classification decision"""
        risk_factors = self.get_risk_factors(analytics)
        
        if decision == "approve":
            if risk_factors:
                return f"Approved despite: {', '.join(risk_factors[:2])}"
            else:
                return "Safe operation, no significant risks detected"
        
        elif decision == "deny":
            if risk_factors:
                return f"Denied due to: {', '.join(risk_factors)}"
            else:
                return f"High risk score: {analytics.risk_score:.3f}"
        
        else:  # review
            return f"Requires review: {', '.join(risk_factors[:3])}"
