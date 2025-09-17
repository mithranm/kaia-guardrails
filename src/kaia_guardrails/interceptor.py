"""
Command interceptor - main entry point for command analysis
"""
import os
import sys
import time
from typing import List

from .analytics import KaiaAnalyticsCollector, CommandAnalytics
from .classifier import RiskClassifier
from .llm_client import LLMClient

class CommandInterceptor:
    """Main command interceptor - always-on analytics collection"""
    
    def __init__(self):
        self.collector = KaiaAnalyticsCollector()
        self.classifier = RiskClassifier()
        self.llm_client = LLMClient()
        
    def intercept_command(self, command: str, args: List[str]) -> bool:
        """
        Intercept and analyze command, return True if should execute
        """
        try:
            # Analyze command
            analytics = self.collector.analyze_command(command, args, os.getcwd())
            
            # Make decision
            decision_result = self._make_decision(analytics)
            
            # Update analytics with decision
            analytics.llm_decision = decision_result.get("llm_decision")
            analytics.llm_confidence = decision_result.get("llm_confidence")
            analytics.llm_reasoning = decision_result.get("llm_reasoning")
            analytics.llm_response_time_ms = decision_result.get("llm_response_time_ms")
            
            analytics.human_decision = decision_result.get("human_decision")
            analytics.human_response_time_ms = decision_result.get("human_response_time_ms")
            
            analytics.final_decision = decision_result["final_decision"]
            analytics.decision_authority = decision_result["decision_authority"]
            
            # Record analytics
            self.collector.record_analytics(analytics)
            
            return analytics.final_decision == "approve"
            
        except Exception as e:
            self.collector.logger.error(f"Interceptor error: {e}")
            # Fail open - don't break user workflows
            return True
    
    def _make_decision(self, analytics: CommandAnalytics) -> dict:
        """Make execution decision using classifier + LLM + human input"""
        
        # Quick local decision for very low risk
        if analytics.risk_score < 0.1:
            return {
                "final_decision": "approve",
                "decision_authority": "auto",
            }
        
        # Get LLM decision for medium+ risk commands
        llm_result = None
        if analytics.risk_score >= 0.1:
            llm_result = self.llm_client.get_decision(analytics)
        
        # Determine if human review needed
        needs_human_review = (
            analytics.risk_score >= 0.6 or
            (llm_result and llm_result["decision"] == "deny") or
            (llm_result and llm_result["confidence"] < 0.7)
        )
        
        if needs_human_review:
            human_result = self._get_human_decision(analytics, llm_result)
            result_dict = {
                "final_decision": human_result["decision"],
                "decision_authority": "human"
            }
            # Add LLM result if it exists
            if llm_result:
                result_dict.update(llm_result)
            # Add human result
            result_dict.update(human_result)
            return result_dict
        
        # Use LLM decision
        if llm_result:
            return {
                **llm_result,
                "final_decision": llm_result["decision"],
                "decision_authority": "llm"
            }
        
        # Fallback to local classifier
        local_decision = self.classifier.classify(analytics)
        return {
            "final_decision": local_decision,
            "decision_authority": "auto"
        }
    
    def _get_human_decision(self, analytics: CommandAnalytics, llm_result: dict = None) -> dict:
        """Get human decision with minimal interruption"""
        start_time = time.time()
        
        # Show context
        print(f"\\n⚠️  Command review: {analytics.full_command}")
        if analytics.risk_score >= 0.5:
            print(f"🚨 Risk level: {analytics.risk_score:.2f}")
        
        if llm_result:
            print(f"🤖 LLM says: {llm_result['decision']} ({llm_result.get('reasoning', '')})")
        
        # Show key risk indicators
        risks = []
        if analytics.is_destructive:
            risks.append("destructive")
        if analytics.uses_sudo:
            risks.append("requires sudo")
        if analytics.targets_system_paths:
            risks.append("system paths")
        if analytics.affects_multiple_files:
            risks.append("multiple files")
        
        if risks:
            print(f"⚡ Risks: {', '.join(risks)}")
        
        try:
            response = input("\\nAllow? (Y/n/always/never): ").strip().lower()
            response_time = (time.time() - start_time) * 1000
            
            if response in ['', 'y', 'yes']:
                return {"decision": "approve", "human_response_time_ms": response_time}
            elif response in ['a', 'always']:
                # TODO: Update auto-approve rules
                return {"decision": "approve", "human_response_time_ms": response_time}
            elif response in ['never']:
                # TODO: Update auto-deny rules  
                return {"decision": "deny", "human_response_time_ms": response_time}
            else:
                return {"decision": "deny", "human_response_time_ms": response_time}
                
        except (KeyboardInterrupt, EOFError):
            return {
                "decision": "deny", 
                "human_response_time_ms": (time.time() - start_time) * 1000
            }

def main():
    """Main entry point for command interception"""
    if len(sys.argv) < 2:
        print("Usage: python -m kaia_guardrails.interceptor <command> [args...]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    interceptor = CommandInterceptor()
    
    try:
        if interceptor.intercept_command(command, args):
            # Execute the original command
            os.execvp(command, [command] + args)
        else:
            print(f"Command denied by guardrails: {command} {' '.join(args)}", file=sys.stderr)
            sys.exit(1)
            
    except FileNotFoundError:
        print(f"Command not found: {command}", file=sys.stderr)
        sys.exit(127)
    except Exception as e:
        print(f"Interceptor error: {e}", file=sys.stderr)
        # Fail open
        try:
            os.execvp(command, [command] + args)
        except FileNotFoundError:
            sys.exit(127)

if __name__ == "__main__":
    main()
