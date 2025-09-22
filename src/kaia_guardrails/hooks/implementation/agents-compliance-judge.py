#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
AGENTS.md Compliance Judge Hook - Context-Aware with Guided JSON

Uses guided JSON generation with vLLM for guaranteed structured output.
Analyzes Claude Code conversation context for real compliance assessment.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from kaia_guardrails.hooks.base import HookBase, HookError

def get_project_root() -> Path:
    """Find the project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

def load_llm_config() -> Dict[str, Any]:
    """Load LLM configuration from pyproject.toml."""
    try:
        import tomllib
        with open(get_project_root() / 'pyproject.toml', 'rb') as f:
            config = tomllib.load(f)
        return config.get('tool', {}).get('vibelint', {}).get('llm', {})
    except Exception as e:
        print(f"[AGENTS-JUDGE-ERROR] Config load failed: {e}", file=sys.stderr)
        return {}

def get_claude_code_context() -> Dict[str, Any]:
    """Extract Claude Code conversation context."""
    context = {
        'tool_name': os.environ.get('CLAUDE_TOOL_NAME', 'unknown'),
        'file_paths': os.environ.get('CLAUDE_FILE_PATHS', ''),
        'user_prompt': os.environ.get('CLAUDE_USER_PROMPT', ''),
        'environment_info': {
            'conda_env': 'mcp-unified' in sys.executable,
            'working_dir': str(Path.cwd()),
            'project_root': str(get_project_root()),
            'in_project': str(Path.cwd()).startswith(str(get_project_root()))
        }
    }
    
    # Add recent context from system health
    try:
        health_file = get_project_root() / '.claude' / 'system-health.json'
        if health_file.exists():
            with open(health_file, 'r') as f:
                health_data = json.load(f)
            context['recent_tools'] = [
                call.get('tool', 'unknown') 
                for call in health_data.get('last_successful_calls', [])
            ][-5:]
    except Exception:
        context['recent_tools'] = []
    
    return context

def load_agents_focus() -> str:
    """Get current focus from AGENTS.instructions.md."""
    try:
        agents_file = get_project_root() / 'AGENTS.instructions.md'
        with open(agents_file, 'r') as f:
            content = f.read()
        
        focus_start = content.find("**Current Focus**:")
        if focus_start != -1:
            focus_line = content[focus_start:focus_start + 500].split('\n')[0]
            return focus_line.replace('**Current Focus**:', '').strip()
        
        return "No current focus defined"
    except Exception:
        return "AGENTS.md not found"

def create_compliance_prompt(context: Dict[str, Any], current_focus: str) -> str:
    """Create compliance assessment prompt for guided JSON."""
    return f"""Assess AGENTS.md compliance for this Claude Code operation.

OPERATION:
Tool: {context['tool_name']}
Files: {context['file_paths']}
Recent: {context.get('recent_tools', [])}

ENVIRONMENT:
Conda: {'✓ mcp-unified' if context['environment_info']['conda_env'] else '✗ wrong env'}
Directory: {'✓ project' if context['environment_info']['in_project'] else '✗ outside project'}
Env Vars: {'✓ set' if context['tool_name'] != 'unknown' else '✗ missing CLAUDE_TOOL_NAME'}

AGENTS.MD REQUIREMENTS:
Current Focus: {current_focus}
- Use mcp-unified conda environment
- Work in project directory
- Set CLAUDE_TOOL_NAME environment variable
- Follow current focus on process management system

Evaluate compliance and provide structured assessment. Consider:
1. Environment setup (30 points)
2. Focus alignment (40 points) 
3. Best practices (30 points)"""

def call_llm_with_guided_json(prompt: str) -> Optional[Dict[str, Any]]:
    """Call LLM with proper guided JSON for structured output."""
    config = load_llm_config()

    api_url = config.get('fast_api_url', 'https://claudiallm-auth-worker.mithran-mohanraj.workers.dev')
    model = config.get('fast_model', 'openai/gpt-oss-20b')

    # JSON schema for compliance assessment
    json_schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100
            },
            "compliant": {
                "type": "boolean"
            },
            "violations": {
                "type": "array",
                "items": {"type": "string"}
            },
            "reasoning": {
                "type": "string"
            }
        },
        "required": ["score", "compliant", "violations", "reasoning"],
        "additionalProperties": False
    }

    # Structured prompt for JSON output
    structured_prompt = f"""{prompt}

Provide your assessment as JSON with:
- score: integer 0-100
- compliant: boolean (true if score >= 70)
- violations: array of specific violation strings
- reasoning: brief explanation of the score"""

    try:
        data = {
            'model': model,
            'temperature': 0.0,
            'max_tokens': 250,  # CRITICAL: Increased for reasoning completion
            'messages': [{'role': 'user', 'content': structured_prompt}],
            'guided_json': json_schema  # CRITICAL: This enables guided decoding
        }

        req = urllib.request.Request(
            f"{api_url}/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=15) as response:  # Increased timeout
            result = json.loads(response.read().decode('utf-8'))

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content')

                if content:
                    try:
                        # Parse the guided JSON output
                        assessment = json.loads(content)

                        # Validate required fields
                        required_fields = ['score', 'compliant', 'violations', 'reasoning']
                        if all(field in assessment for field in required_fields):
                            assessment['block'] = not assessment['compliant']
                            print(f"[AGENTS-JUDGE-DEBUG] LLM guided JSON success: {assessment['score']}/100", file=sys.stderr)
                            return assessment
                        else:
                            print(f"[AGENTS-JUDGE-DEBUG] LLM JSON missing fields: {content}", file=sys.stderr)

                    except json.JSONDecodeError as e:
                        print(f"[AGENTS-JUDGE-DEBUG] LLM JSON parse error: {e}, content: '{content}'", file=sys.stderr)

                else:
                    print(f"[AGENTS-JUDGE-DEBUG] LLM returned null content", file=sys.stderr)

        return None

    except Exception as e:
        print(f"[AGENTS-JUDGE-ERROR] LLM call failed: {e}", file=sys.stderr)
        return None

def create_deterministic_assessment(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create deterministic compliance assessment as fallback."""
    score = 0
    violations = []
    
    # Environment variables (40 points)
    if context['tool_name'] != 'unknown':
        score += 40
    else:
        violations.append('Missing CLAUDE_TOOL_NAME environment variable')
    
    # Conda environment (30 points)
    if context['environment_info']['conda_env']:
        score += 30
    else:
        violations.append('Not using mcp-unified conda environment')
    
    # Working directory (30 points)
    if context['environment_info']['in_project']:
        score += 30
    else:
        violations.append('Not working in project directory')
    
    return {
        'score': score,
        'compliant': score >= 70,
        'violations': violations,
        'block': not context['environment_info']['in_project'],
        'reasoning': f'Deterministic assessment: {score}/100 based on env vars, conda, and directory',
        'source': 'deterministic'
    }

def save_compliance_log(context: Dict[str, Any], result: Dict[str, Any]):
    """Save compliance assessment log."""
    try:
        claude_dir = get_project_root() / '.claude'
        claude_dir.mkdir(exist_ok=True)
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'tool': context['tool_name'],
            'assessment': result
        }
        
        log_file = claude_dir / 'compliance-assessments.jsonl'
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        # Keep reasonable size
        if log_file.stat().st_size > 200000:  # 200KB
            lines = log_file.read_text().split('\n')[-200:]
            log_file.write_text('\n'.join(lines))
            
    except Exception as e:
        print(f"[AGENTS-JUDGE-ERROR] Failed to save log: {e}", file=sys.stderr)

def main():
    """Main context-aware compliance judge with guided JSON."""
    # Get Claude Code context
    context = get_claude_code_context()
    current_focus = load_agents_focus()
    
    # Try LLM assessment with guided JSON
    prompt = create_compliance_prompt(context, current_focus)
    llm_result = call_llm_with_guided_json(prompt)
    
    if llm_result:
        result = llm_result
        result['source'] = 'llm_simple_scoring'
    else:
        # Fallback to deterministic assessment
        print("[AGENTS-JUDGE-DEBUG] LLM failed, using deterministic assessment", file=sys.stderr)
        result = create_deterministic_assessment(context)
    
    # Save assessment log
    save_compliance_log(context, result)
    
    # Generate status message
    score = result.get('score', 0)
    source = result.get('source', 'unknown')
    
    if score >= 90:
        status = "✅ EXCELLENT"
    elif score >= 75:
        status = "⚠️ GOOD"
    elif score >= 60:
        status = "🔶 ACCEPTABLE"
    else:
        status = "🚫 POOR"
    
    print(f"[AGENTS-JUDGE] {status} Compliance: {score}/100 ({source})", file=sys.stderr)
    
    # Show violations
    violations = result.get('violations', [])
    if violations:
        print(f"[AGENTS-JUDGE] Issues: {', '.join(violations)}", file=sys.stderr)
    
    # Show reasoning if available
    reasoning = result.get('reasoning', '')
    if reasoning:
        print(f"[AGENTS-JUDGE] Reasoning: {reasoning}", file=sys.stderr)
    
    # Remind about AGENTS.md if needed
    if context['tool_name'] == 'unknown':
        print("[AGENTS-JUDGE] 💡 Reminder: Set CLAUDE_TOOL_NAME and CLAUDE_FILE_PATHS per AGENTS.md", file=sys.stderr)
    
    # Block for critical violations
    if result.get('block', False):
        print("[AGENTS-JUDGE] 🚫 BLOCKING: Critical compliance violation", file=sys.stderr)
        sys.exit(1)

class AgentsComplianceJudgeHook(HookBase):
    """Hook that judges compliance with AGENTS.md guidelines."""

    def __init__(self):
        super().__init__(name="agents_compliance_judge", priority=50)

    def run(self, context: Dict[str, Any]) -> Any:
        """Run compliance assessment."""
        # Get Claude Code context
        claude_context = get_claude_code_context()
        current_focus = load_agents_focus()

        # Try LLM assessment with guided JSON
        prompt = create_compliance_prompt(claude_context, current_focus)
        llm_result = call_llm_with_guided_json(prompt)

        if llm_result:
            result = llm_result
            result['source'] = 'llm_simple_scoring'
        else:
            # Fallback to deterministic assessment
            result = create_deterministic_assessment(claude_context)

        # Save assessment log
        save_compliance_log(claude_context, result)

        # Return result for orchestrator
        return result

if __name__ == '__main__':
    main()
