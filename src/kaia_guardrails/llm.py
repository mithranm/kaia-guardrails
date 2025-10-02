"""
Kaia Guardrails LLM Integration

Imports LLM orchestrator utilities from vibelint and provides kaia-specific
functionality for AGENTS.md compliance checking.

This module:
- Imports the authoritative LLM implementation from vibelint
- Provides kaia-specific configuration and helpers
- Implements structured compliance assessment
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add vibelint to Python path so we can import from it
vibelint_path = Path(__file__).parent.parent.parent.parent.parent / "tools" / "vibelint" / "src"
if vibelint_path.exists():
 sys.path.insert(0, str(vibelint_path))

try:
 # Import from vibelint (authoritative implementation)
 from vibelint.llm_config import find_project_root
 from vibelint.llm_config import get_llm_config as get_vibelint_llm_config
 from vibelint.llm_config import load_env_files, load_toml_config
 from vibelint.llm_orchestrator import (LLMBackend, LLMOrchestrator,
                                        LLMRequest, LLMResponse, LLMRole,
                                        create_llm_orchestrator)
except ImportError as e:
 raise ImportError(f"Failed to import from vibelint: {e}. Make sure vibelint is properly installed.") from e


def get_kaia_config() -> Dict[str, Any]:
 """Get kaia guardrails configuration."""
 project_root = find_project_root()
 load_env_files(project_root)
 
 # Load base configuration from project root
 base_config = load_toml_config(project_root / "pyproject.toml")
 
 # Load development overrides from project root
 dev_config = load_toml_config(project_root / "dev.pyproject.toml")
 
 # Merge configurations
 merged_config = {}
 
 # Start with base config
 if "tool" in base_config and "kaia_guardrails" in base_config["tool"]:
 merged_config = base_config["tool"]["kaia_guardrails"].copy()
 
 # Apply dev overrides
 if "tool" in dev_config and "kaia_guardrails" in dev_config["tool"]:
 merged_config.update(dev_config["tool"]["kaia_guardrails"])
 
 return merged_config


def get_kaia_llm_config() -> Dict[str, Any]:
 """Get LLM configuration for kaia guardrails."""
 kaia_config = get_kaia_config()
 
 # Check if kaia has its own LLM config
 if "llm" in kaia_config:
 llm_config = kaia_config["llm"].copy()
 else:
 # Use legacy judge_llm_* format or fall back to vibelint config
 llm_config = {}
 
 # Map legacy kaia config to new format
 if "judge_llm_base_url" in kaia_config:
 llm_config.update({
 "fast_api_url": kaia_config["judge_llm_base_url"],
 "fast_model": kaia_config.get("judge_llm_model"),
 "fast_backend": kaia_config.get("judge_llm_backend", "vllm"),
 "fast_temperature": kaia_config.get("judge_temperature", 0.0),
 "fast_max_tokens": kaia_config.get("judge_max_tokens", 1000),
 })
 else:
 # Fall back to vibelint config
 llm_config = get_vibelint_llm_config()
 
 # Apply environment overrides
 env_overrides = {
 "fast_api_url": os.getenv("KAIA_LLM_API_URL") or os.getenv("KAIA_JUDGE_LLM_BASE_URL"),
 "fast_model": os.getenv("KAIA_LLM_MODEL") or os.getenv("KAIA_JUDGE_LLM_MODEL"),
 "fast_backend": os.getenv("KAIA_LLM_BACKEND") or os.getenv("KAIA_JUDGE_LLM_BACKEND"),
 "fast_temperature": _get_env_float("KAIA_LLM_TEMPERATURE") or _get_env_float("KAIA_JUDGE_TEMPERATURE"),
 "fast_max_tokens": _get_env_int("KAIA_LLM_MAX_TOKENS") or _get_env_int("KAIA_JUDGE_MAX_TOKENS"),
 }
 
 # Apply non-None overrides
 for key, value in env_overrides.items():
 if value is not None:
 llm_config[key] = value
 
 return llm_config


def create_kaia_orchestrator() -> LLMOrchestrator:
 """Create LLM orchestrator configured for kaia guardrails."""
 config = {"llm": get_kaia_llm_config()}
 return create_llm_orchestrator(config)


def call_llm_with_compliance_schema(prompt: str) -> Dict[str, Any]:
 """
 Call LLM with AGENTS.md compliance assessment schema.
 
 This is the main function used by kaia guardrails for compliance checking.
 Features intelligent fallback from fast LLM to orchestrator LLM.
 
 FAILS LOUD: If both LLMs fail, raises exception to indicate infrastructure issues.
 
 Args:
 prompt: Compliance assessment prompt
 
 Returns:
 Structured compliance assessment dictionary
 
 Raises:
 RuntimeError: If both fast and orchestrator LLMs fail (infrastructure issue)
 ValueError: If LLM orchestrator cannot be created (configuration issue)
 """
 try:
 orchestrator = create_kaia_orchestrator()
 except Exception as e:
 config_info = get_kaia_llm_config()
 error_msg = (
 f"[KAIA-CRITICAL] Failed to create LLM orchestrator - check configuration!\n"
 f"Error: {e}\n"
 f"Config: {config_info}\n"
 f"This indicates a serious configuration or dependency issue."
 )
 print(error_msg)
 raise ValueError(error_msg) from e
 
 # Enhanced prompt for compliance assessment
 structured_prompt = f"""{prompt}

Assess this code for AGENTS.md compliance and provide a structured assessment.

Respond with valid JSON containing:
- score: integer from 0 to 100
- compliant: boolean (true if score >= 70)
- violations: array of specific violation strings
- reasoning: brief explanation of the assessment
- severity: "low", "medium", or "high"
- suggestions: array of improvement suggestions

Example format:
{{
 "score": 85,
 "compliant": true,
 "violations": [],
 "reasoning": "Code follows most best practices with minor issues",
 "severity": "low",
 "suggestions": ["Add error handling", "Improve documentation"]
}}

Respond with ONLY valid JSON, no other text:"""

 request = LLMRequest(
 content=structured_prompt,
 task_type="compliance_assessment",
 require_json=True,
 temperature=0.0,
 max_tokens=1000
 )
 
 try:
 response = orchestrator.process_request(request)
 
 if response.parsed_json:
 # Add the 'block' field based on compliance
 result = response.parsed_json.copy()
 result['block'] = not result.get('compliant', False)
 return result
 else:
 # Try fallback text parsing if JSON parsing failed
 fallback_result = _parse_compliance_text(response.content)
 if fallback_result:
 return fallback_result
 else:
 # Even fallback parsing failed - this is a serious issue
 error_msg = (
 f"[KAIA-CRITICAL] LLM returned unparseable response!\n"
 f"Response role: {response.role_used.value}\n"
 f"Response backend: {response.backend_used.value}\n"
 f"Raw content: {response.content[:500]}...\n"
 f"This indicates the LLM is not following JSON format instructions."
 )
 print(error_msg)
 raise RuntimeError(error_msg)
 
 except RuntimeError as e:
 # This comes from the orchestrator when both LLMs fail
 config_info = get_kaia_llm_config()
 error_msg = (
 f"[KAIA-CRITICAL] BOTH FAST AND ORCHESTRATOR LLMS FAILED!\n"
 f"This indicates serious infrastructure issues:\n"
 f"- Network connectivity problems\n"
 f"- LLM server downtime\n"
 f"- Authentication/API key issues\n"
 f"- Model loading problems\n\n"
 f"Original error: {e}\n"
 f"Current LLM config: {config_info}\n\n"
 f"ACTION REQUIRED: Check LLM server status and network connectivity!"
 )
 print(error_msg)
 raise RuntimeError(error_msg) from e
 
 except Exception as e:
 # Unexpected error - also fail loud
 config_info = get_kaia_llm_config()
 error_msg = (
 f"[KAIA-CRITICAL] Unexpected error in LLM compliance assessment!\n"
 f"Error type: {type(e).__name__}\n"
 f"Error: {e}\n"
 f"Config: {config_info}\n"
 f"This indicates an unexpected system issue."
 )
 print(error_msg)
 raise RuntimeError(error_msg) from e


def _parse_compliance_text(content: str) -> Dict[str, Any]:
 """
 Fallback text parsing for compliance assessment.
 
 FAILS LOUD: If parsing fails completely, raises exception instead of returning None.
 This indicates the LLM is not following instructions properly.
 """
 try:
 # Try to extract JSON from the response
 import json
 import re

 # Look for JSON-like content
 json_match = re.search(r'\{.*\}', content, re.DOTALL)
 if json_match:
 json_str = json_match.group(0)
 parsed = json.loads(json_str)
 
 # Ensure required fields
 result = {
 "score": parsed.get("score", 50),
 "compliant": parsed.get("compliant", False),
 "violations": parsed.get("violations", []),
 "reasoning": parsed.get("reasoning", "Unable to parse assessment"),
 "severity": parsed.get("severity", "medium"),
 "suggestions": parsed.get("suggestions", [])
 }
 result['block'] = not result['compliant']
 return result
 else:
 # No JSON found in response - this is a serious issue
 error_msg = (
 f"[KAIA-CRITICAL] No JSON found in LLM response!\n"
 f"Raw content: {content[:500]}...\n"
 f"The LLM is not following JSON format instructions."
 )
 raise RuntimeError(error_msg)
 
 except json.JSONDecodeError as e:
 error_msg = (
 f"[KAIA-CRITICAL] Invalid JSON in LLM response!\n"
 f"JSON error: {e}\n"
 f"Raw content: {content[:500]}...\n"
 f"The LLM produced malformed JSON."
 )
 raise RuntimeError(error_msg) from e
 
 except Exception as e:
 error_msg = (
 f"[KAIA-CRITICAL] Unexpected error in fallback parsing!\n"
 f"Error: {e}\n"
 f"Raw content: {content[:500]}...\n"
 f"This indicates a system parsing issue."
 )
 raise RuntimeError(error_msg) from e


def _get_env_float(key: str) -> Optional[float]:
 """Get float value from environment variable."""
 value = os.getenv(key)
 if value is not None:
 try:
 return float(value)
 except ValueError:
 return None
 return None


def _get_env_int(key: str) -> Optional[int]:
 """Get integer value from environment variable."""
 value = os.getenv(key)
 if value is not None:
 try:
 return int(value)
 except ValueError:
 return None
 return None


# Export public interface
__all__ = [
 # Main functions
 "call_llm_with_compliance_schema",
 "create_kaia_orchestrator",
 "get_kaia_config",
 "get_kaia_llm_config",
 
 # Re-export from vibelint
 "LLMOrchestrator", 
 "LLMRequest",
 "LLMResponse", 
 "LLMRole",
 "LLMBackend"
]
