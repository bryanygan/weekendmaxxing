"""Application settings — reads configuration from environment variables."""

import os

USE_LOCAL_LLM: bool = os.getenv("USE_LOCAL_LLM", "true").lower() in ("true", "1", "yes")
LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b")
