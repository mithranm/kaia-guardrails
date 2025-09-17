"""
LLM client for command risk assessment
"""
import json
import time
import requests
from typing import Dict, Optional

from .analytics import CommandAnalytics

class LLMClient:
    """Client for LLM-based risk assessment"""
    
    def __init__(self, endpoint: str = "http://100.94.250.88:8001"):
        self.endpoint = endpoint
        self.model = "openai/gpt-oss-20b"
        self.timeout = 5.0
        
    def get_decision(self, analytics: CommandAnalytics) -> Optional[Dict]:
        """Get LLM decision for command"""
        start_time = time.time()
        
        try:
            prompt = self._build_prompt(analytics)
            
            response = requests.post(
                f"{self.endpoint}/v1/completions",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "max_tokens": 150,
                    "temperature": 0.1,
                    "stop": ["}"]
                },
                timeout=self.timeout
            )
            
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result_text = response.json()["choices"][0]["text"]
                
                # Clean up response
                if not result_text.strip().endswith('}'):
                    result_text += "}"
                
                try:
                    result = json.loads(result_text)
                    return {
                        "llm_decision": result.get("decision", "approve"),
                        "llm_confidence": float(result.get("confidence", 0.5)),
                        "llm_reasoning": result.get("reasoning", "LLM analysis"),
                        "llm_response_time_ms": response_time,
                        "decision": result.get("decision", "approve"),
                        "confidence": float(result.get("confidence", 0.5)),
                        "reasoning": result.get("reasoning", "LLM analysis")
                    }
                except json.JSONDecodeError:
                    # Fallback parsing
                    decision = "approve" if "approve" in result_text.lower() else "deny"
                    return {
                        "llm_decision": decision,
                        "llm_confidence": 0.6,
                        "llm_reasoning": f"Parsed: {result_text[:50]}...",
                        "llm_response_time_ms": response_time,
                        "decision": decision,
                        "confidence": 0.6,
                        "reasoning": f"Parsed: {result_text[:50]}..."
                    }
            else:
                return None
                
        except Exception as e:
            # LLM unavailable - return None to fall back to other methods
            return None
    
    def _build_prompt(self, analytics: CommandAnalytics) -> str:
        """Build LLM prompt with analytics context"""
        
        context_info = []
        if analytics.is_git_repo:
            context_info.append("git repository")
        if analytics.is_python_project:
            context_info.append("Python project")
        if analytics.claude_code_active:
            context_info.append("Claude Code session")
        
        risk_info = []
        if analytics.is_destructive:
            risk_info.append("destructive operation")
        if analytics.uses_sudo:
            risk_info.append("requires sudo")
        if analytics.targets_system_paths:
            risk_info.append("targets system paths")
        if analytics.affects_multiple_files:
            risk_info.append("affects multiple files")
        
        compliance_info = []
        if analytics.vibelint_compliant is False:
            compliance_info.append("vibelint violations")
        if analytics.project_rules_compliant is False:
            compliance_info.append("project rule violations")
        
        prompt = f"""You are a security guardian for command execution. Analyze this command:

COMMAND: {analytics.full_command}

CONTEXT:
- Working directory: {analytics.cwd}
- Environment: {', '.join(context_info) if context_info else 'standard'}
- Risk score: {analytics.risk_score:.3f}

RISK FACTORS: {', '.join(risk_info) if risk_info else 'none detected'}

COMPLIANCE ISSUES: {', '.join(compliance_info) if compliance_info else 'none detected'}

ANALYSIS CRITERIA:
1. APPROVE: Safe operations, follows best practices, low risk
2. DENY: Dangerous operations, security risks, policy violations
3. Consider: Is this reasonable for development work?

Respond with JSON:
{{"decision": "approve|deny", "confidence": 0.85, "reasoning": "brief explanation focusing on key factors"}}"""
        
        return prompt
    
    def is_available(self) -> bool:
        """Check if LLM service is available"""
        try:
            response = requests.get(f"{self.endpoint}/v1/models", timeout=2.0)
            return response.status_code == 200
        except:
            return False
