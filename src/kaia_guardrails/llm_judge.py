"""
LLM Judge Utility

Simple yes/no LLM judgments for guardrails using vibelint's fast LLM configuration.
Provides consistent, maintainable interface for all guardrail decisions.
"""
import json
import urllib.request
from typing import Dict, Any
from .hooks.fast_judge_util import get_fast_judge_config


def ask_llm_yesno(question: str, context: str = "") -> bool:
    """
    Ask the LLM a yes/no question and get a boolean answer.

    Throws exception if LLM is unavailable - no fallbacks, fail hard.

    Args:
        question: The yes/no question to ask
        context: Additional context for the decision

    Returns:
        bool: True for yes, False for no

    Raises:
        Exception: If LLM call fails or returns invalid response
    """
    config = get_fast_judge_config()

    # Minimal JSON schema - just yes/no
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

    # Simple, clear prompt
    prompt = f"""Question: {question}

Context:
{context}

Answer only "yes" or "no" in JSON format: {{"answer": "yes"}} or {{"answer": "no"}}"""

    try:
        data = {
            'model': config['model'],
            'temperature': config.get('temperature', 0.0),  # Zero temp for consistent decisions
            'max_tokens': 100,  # Enough tokens for JSON response
            'messages': [{'role': 'user', 'content': prompt}],
            'guided_json': json_schema
        }

        req = urllib.request.Request(
            f"{config['api_url']}/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=config.get('timeout', 15)) as response:
            result = json.loads(response.read().decode('utf-8'))

            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                content = choice['message'].get('content')
                reasoning = choice['message'].get('reasoning_content')

                # Log thinking tokens if available
                if reasoning:
                    print(f"[LLM-JUDGE-THINKING] {reasoning}")

                if content:
                    try:
                        judgment = json.loads(content)
                        answer_str = judgment.get('answer', 'no')

                        if answer_str not in ['yes', 'no']:
                            raise Exception(f"LLM returned invalid answer: {answer_str}")

                        # Log the decision
                        print(f"[LLM-JUDGE-DECISION] Question: {question[:100]}... -> {answer_str}")

                        return answer_str == 'yes'

                    except json.JSONDecodeError as e:
                        raise Exception(f"Failed to parse LLM JSON response: {content}") from e

        raise Exception("LLM returned empty response")

    except Exception as e:
        # Re-raise all exceptions - no fallbacks, fail hard
        raise Exception(f"LLM judgment failed: {e}") from e


def validate_file_placement(file_path: str, content: str, project_structure: str) -> bool:
    """
    Validate if a file should be placed at the given location.

    Args:
        file_path: Relative path where file will be created
        content: File content preview
        project_structure: Description of existing project structure

    Returns:
        bool: True if placement is appropriate, False if inappropriate

    Raises:
        Exception: If LLM validation fails
    """
    question = "Is this file placement appropriate for the project structure?"

    context = f"""Project Structure:
{project_structure}

Proposed new file: {file_path}
File content preview: {content[:500]}...

Consider:
1. Does the file belong in the proposed directory?
2. Does it follow existing naming conventions?
3. Is it placed at the appropriate hierarchy level?
4. Does it follow security best practices?
5. Does it match project organization patterns?

Be especially careful about:
- Security files (passwords, secrets, keys) in wrong locations
- Configuration files in implementation directories
- Test/temp files in production areas
- Files with unclear purposes in project root"""

    return ask_llm_yesno(question, context)


def validate_code_change(change_description: str, context: str) -> bool:
    """
    Validate if a code change is appropriate.

    Args:
        change_description: Description of the code change
        context: Context about the code being changed

    Returns:
        bool: True if change is appropriate, False if inappropriate

    Raises:
        Exception: If LLM validation fails
    """
    question = "Is this code change appropriate and safe?"

    full_context = f"""Code Change: {change_description}

Context: {context}

Consider:
1. Does the change follow best practices?
2. Is it safe and secure?
3. Does it maintain code quality?
4. Is it consistent with existing patterns?"""

    return ask_llm_yesno(question, full_context)