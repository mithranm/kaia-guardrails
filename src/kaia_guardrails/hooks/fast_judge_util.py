"""
Fast Judge Utility

Quick yes/no LLM calls with JSON generation for guardrail decisions.
"""
import json
import urllib.request
from typing import Dict, Any, Optional


def get_fast_judge_config() -> Dict[str, Any]:
    """Get LLM configuration from vibelint config files directly."""
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
        if (current / 'dev.pyproject.toml').exists():
            break
        current = current.parent
    else:
        raise ValueError("Could not find main project root with dev.pyproject.toml")

    project_root = current

    # Load production config
    prod_config = {}
    prod_config_path = project_root / 'pyproject.toml'
    if prod_config_path.exists():
        with open(prod_config_path, 'rb') as f:
            prod_config = tomllib.load(f)

    # Load dev overrides
    dev_config = {}
    dev_config_path = project_root / 'dev.pyproject.toml'
    if dev_config_path.exists():
        with open(dev_config_path, 'rb') as f:
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
    vibelint_config = merged_config.get('tool', {}).get('vibelint', {})
    llm_config = vibelint_config.get('llm', {})

    # Validate required fields for fast LLM
    fast_api_url = llm_config.get('fast_api_url')
    if not fast_api_url:
        raise ValueError("REQUIRED CONFIG MISSING: 'fast_api_url' not found in vibelint.llm config")

    fast_model = llm_config.get('fast_model')
    if not fast_model:
        raise ValueError("REQUIRED CONFIG MISSING: 'fast_model' not found in vibelint.llm config")

    return {
        'api_url': fast_api_url,
        'model': fast_model,
        'api_key': llm_config.get('fast_api_key', ''),
        'timeout': vibelint_config.get('timeout', 15),
        'temperature': llm_config.get('fast_temperature', 0.1),
        'max_tokens': llm_config.get('fast_max_tokens', 300)
    }


def call_fast_judge_yesno(question: str, context: str = "") -> Dict[str, Any]:
    """
    Call fast LLM for quick yes/no judgment with reasoning.

    Args:
        question: The yes/no question to ask
        context: Additional context for the decision

    Returns:
        Dict with 'answer' (bool), 'reasoning' (str), 'confidence' (float)
    """
    config = get_fast_judge_config()

    # Simple yes/no JSON schema - no reasoning needed
    json_schema = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "enum": ["yes", "no"]
            }
        },
        "required": ["answer"],
        "additionalProperties": False
    }

    # Build structured prompt
    prompt = f"""Question: {question}

Context:
{context}

Respond with just "yes" or "no" in JSON format: {{"answer": "yes"}} or {{"answer": "no"}}"""

    try:
        data = {
            'model': config['model'],
            'temperature': config.get('temperature', 0.1),
            'max_tokens': config.get('max_tokens', 300),
            'messages': [{'role': 'user', 'content': prompt}],
            'guided_json': json_schema
        }

        req = urllib.request.Request(
            f"{config['api_url']}/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=config['timeout']) as response:
            result = json.loads(response.read().decode('utf-8'))

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content')

                if content:
                    try:
                        judgment = json.loads(content)
                        answer_str = judgment.get('answer', 'no')
                        return {
                            'answer': answer_str == 'yes',
                            'success': True
                        }
                    except json.JSONDecodeError:
                        return {
                            'answer': False,
                            'success': False,
                            'error': f'Failed to parse LLM response: {content}'
                        }

        return {
            'answer': False,
            'success': False,
            'error': 'No response from LLM'
        }

    except Exception as e:
        return {
            'answer': False,
            'success': False,
            'error': f'LLM call failed: {e}'
        }


def call_fast_judge_choice(question: str, choices: list, context: str = "") -> Dict[str, Any]:
    """
    Call fast LLM for multiple choice judgment.

    Args:
        question: The question to ask
        choices: List of possible choices
        context: Additional context for the decision

    Returns:
        Dict with 'choice' (str), 'reasoning' (str), 'confidence' (float)
    """
    config = get_fast_judge_config()

    # Multiple choice JSON schema
    json_schema = {
        "type": "object",
        "properties": {
            "choice": {
                "type": "string",
                "enum": choices
            },
            "reasoning": {
                "type": "string"
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0
            }
        },
        "required": ["choice", "reasoning", "confidence"],
        "additionalProperties": False
    }

    choices_str = "\n".join([f"- {choice}" for choice in choices])

    prompt = f"""Question: {question}

Available choices:
{choices_str}

Context:
{context}

Select the most appropriate choice and provide brief reasoning.

Respond in JSON format with:
- choice: one of the available choices (exact match)
- reasoning: brief explanation (1-2 sentences)
- confidence: 0.0 to 1.0 confidence level"""

    try:
        data = {
            'model': config['model'],
            'temperature': 0.1,
            'max_tokens': 150,
            'messages': [{'role': 'user', 'content': prompt}],
            'guided_json': json_schema
        }

        req = urllib.request.Request(
            f"{config['api_url']}/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=config['timeout']) as response:
            result = json.loads(response.read().decode('utf-8'))

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content')

                if content:
                    try:
                        judgment = json.loads(content)
                        return {
                            'choice': judgment.get('choice', choices[0]),
                            'reasoning': judgment.get('reasoning', 'No reasoning provided'),
                            'confidence': judgment.get('confidence', 0.0),
                            'success': True
                        }
                    except json.JSONDecodeError:
                        return {
                            'choice': choices[0],
                            'reasoning': f'Failed to parse LLM response: {content}',
                            'confidence': 0.0,
                            'success': False
                        }

        return {
            'choice': choices[0],
            'reasoning': 'No response from LLM',
            'confidence': 0.0,
            'success': False
        }

    except Exception as e:
        return {
            'choice': choices[0],
            'reasoning': f'LLM call failed: {e}',
            'confidence': 0.0,
            'success': False
        }