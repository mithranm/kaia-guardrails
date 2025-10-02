"""
Orchestrator Judge Utility

Fallback LLM judge using orchestrator endpoint with llama.cpp JSON schema support.
Uses response_format parameter instead of guided_json for llama.cpp compatibility.
"""

import json
import urllib.request
from typing import Any, Dict


def get_orchestrator_judge_config() -> Dict[str, Any]:
 """Get orchestrator LLM configuration from vibelint config files."""
 import sys
 from pathlib import Path

 if sys.version_info >= (3, 11):
 import tomllib
 else:
 try:
 import tomli as tomllib
 except ImportError as e:
 raise ValueError(
 "Requires Python 3.11+ or the 'tomli' package to parse pyproject.toml"
 ) from e

 # Find main project root (where dev.pyproject.toml exists)
 current = Path.cwd()
 while current.parent != current:
 if (current / "dev.pyproject.toml").exists():
 break
 current = current.parent
 else:
 raise ValueError("Could not find main project root with dev.pyproject.toml")

 project_root = current

 # Load production config
 prod_config = {}
 prod_config_path = project_root / "pyproject.toml"
 if prod_config_path.exists():
 with open(prod_config_path, "rb") as f:
 prod_config = tomllib.load(f)

 # Load dev overrides
 dev_config = {}
 dev_config_path = project_root / "dev.pyproject.toml"
 if dev_config_path.exists():
 with open(dev_config_path, "rb") as f:
 dev_config = tomllib.load(f)

 # Merge configs (dev overrides prod)
 def deep_merge(base: dict, override: dict) -> dict:
 result = base.copy()
 for key, value in override.items():
 if key in result and isinstance(result[key], dict) and isinstance(value, dict):
 result[key] = deep_merge(result[key], value)
 else:
 result[key] = value
 return result

 merged_config = deep_merge(prod_config, dev_config)

 # Extract vibelint LLM config
 vibelint_config = merged_config.get("tool", {}).get("vibelint", {})
 llm_config = vibelint_config.get("llm", {})

 # Validate required fields for orchestrator LLM
 orchestrator_api_url = llm_config.get("orchestrator_api_url")
 if not orchestrator_api_url:
 raise ValueError(
 "REQUIRED CONFIG MISSING: 'orchestrator_api_url' not found in vibelint.llm config"
 )

 orchestrator_model = llm_config.get("orchestrator_model")
 if not orchestrator_model:
 raise ValueError(
 "REQUIRED CONFIG MISSING: 'orchestrator_model' not found in vibelint.llm config"
 )

 return {
 "api_url": orchestrator_api_url,
 "model": orchestrator_model,
 "api_key": llm_config.get("orchestrator_api_key", ""),
 "timeout": llm_config.get("timeout", 30),
 }


def ask_orchestrator_llm_yesno(question: str, context: str = "") -> bool:
 """
 Ask the orchestrator LLM a yes/no question using llama.cpp JSON schema format.

 Uses response_format parameter instead of guided_json for llama.cpp compatibility.

 Args:
 question: The yes/no question to ask
 context: Additional context for the decision

 Returns:
 bool: True for yes, False for no

 Raises:
 Exception: If LLM call fails or returns invalid response
 """
 config = get_orchestrator_judge_config()

 # JSON schema for llama.cpp response_format
 json_schema = {
 "type": "object",
 "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
 "required": ["answer"],
 "additionalProperties": False,
 }

 # Simple, clear prompt
 prompt = f"""Question: {question}

Context:
{context}

Answer only "yes" or "no" in JSON format: {{"answer": "yes"}} or {{"answer": "no"}}"""

 try:
 # llama.cpp format with response_format instead of guided_json
 data = {
 "model": config["model"],
 "temperature": 0.0, # Zero temp for consistent decisions
 "max_tokens": 200, # At least 200 tokens for coherent response
 "messages": [{"role": "user", "content": prompt}],
 "response_format": { # llama.cpp JSON schema format
 "type": "json_schema",
 "schema": json_schema,
 },
 }

 req = urllib.request.Request(
 f"{config['api_url']}/v1/chat/completions",
 data=json.dumps(data).encode("utf-8"),
 headers={
 "Content-Type": "application/json",
 "User-Agent": "kaia-guardrails/orchestrator-judge (github.com/mithranm/kaia-guardrails)",
 },
 )

 with urllib.request.urlopen(req, timeout=config.get("timeout", 30)) as response:
 result = json.loads(response.read().decode("utf-8"))

 if "choices" in result and len(result["choices"]) > 0:
 choice = result["choices"][0]
 content = choice["message"].get("content")
 reasoning = choice["message"].get("reasoning_content")

 # Log thinking tokens if available
 if reasoning:
 print(f"[ORCHESTRATOR-JUDGE-THINKING] {reasoning}")

 if content:
 try:
 judgment = json.loads(content)
 answer_str = judgment.get("answer", "no")

 if answer_str not in ["yes", "no"]:
 raise Exception(
 f"Orchestrator LLM returned invalid answer: {answer_str}"
 )

 # Log the decision
 print(
 f"[ORCHESTRATOR-JUDGE-DECISION] Question: {question[:100]}... -> {answer_str}"
 )

 return answer_str == "yes"

 except json.JSONDecodeError as e:
 raise Exception(
 f"Failed to parse orchestrator LLM JSON response: {content}"
 ) from e

 raise Exception("Orchestrator LLM returned empty response")

 except Exception as e:
 # Re-raise all exceptions - no fallbacks, fail hard
 raise Exception(f"Orchestrator LLM judgment failed: {e}") from e


def validate_file_placement_orchestrator(
 file_path: str, content: str, project_structure: str
) -> bool:
 """
 Validate if a file should be placed at the given location using orchestrator LLM.

 Args:
 file_path: Relative path where file will be created
 content: File content preview
 project_structure: Description of existing project structure

 Returns:
 bool: True if file placement is appropriate, False otherwise

 Raises:
 Exception: If orchestrator LLM call fails
 """
 question = f"""Should the file '{file_path}' be created at this location in the project?

Consider:
- Does the path follow project conventions?
- Is the content appropriate for this location?
- Would this file fit the existing structure?"""

 context = f"""File path: {file_path}

Content preview:
{content[:500]}{'...' if len(content) > 500 else ''}

Project structure:
{project_structure}"""

 return ask_orchestrator_llm_yesno(question, context)
