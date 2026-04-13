"""JSON extractor — pulls structured JSON from free-form LLM output."""

import json
import re


def extract_json(raw: str) -> list | dict:
    """Parse and return the first valid JSON object or array found in raw text.

    Tries in order:
    1. Strip markdown code fences and json.loads the full string.
    2. Regex-find the first [...] block and parse it.
    3. Regex-find the first {...} block and parse it.
    4. If all fail, print a warning and return [].
    """
    # Strip markdown fences
    stripped = re.sub(r"```(?:json)?\s*", "", raw).strip()
    stripped = stripped.replace("```", "").strip()

    # Attempt 1: parse the whole stripped string
    try:
        result = json.loads(stripped)
        if isinstance(result, (list, dict)):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: find first [...] block
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Attempt 3: find first {...} block
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    print(f"[json_extractor] WARNING: could not extract JSON from: {raw[:200]!r}")
    return []
