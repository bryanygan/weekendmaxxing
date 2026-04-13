"""LLM client — unified interface to local or remote language models."""

from typing import Any


class LLMClient:
    """Send prompts to the configured LLM and return structured responses.

    Supports both local (Ollama/LM Studio) and remote endpoints.
    Reads connection details from config.settings.
    """

    def query(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """Send a prompt to the LLM and return the parsed response."""
        pass
