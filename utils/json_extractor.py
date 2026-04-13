"""JSON extractor — pulls structured JSON from free-form LLM output."""

from typing import Any


def extract_json(text: str) -> dict[str, Any] | list:
    """Parse and return the first valid JSON object or array found in the text.

    Handles common LLM output patterns like markdown code fences
    and leading/trailing prose around JSON blocks.
    """
    pass
