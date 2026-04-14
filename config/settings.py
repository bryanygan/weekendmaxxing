"""Application settings — reads configuration from environment variables."""

import os

# LLM
USE_LOCAL_LLM: bool = os.getenv("USE_LOCAL_LLM", "true").lower() in ("true", "1", "yes")
LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b")

# Email notifications (optional — set env vars to enable)
EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
EMAIL_SMTP_HOST: str = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SENDER: str = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT: str = os.getenv("EMAIL_RECIPIENT", "")

# Flight/Hotel APIs (optional — system falls back to scrapers if not set)
AMADEUS_API_KEY: str = os.getenv("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET: str = os.getenv("AMADEUS_API_SECRET", "")
KIWI_API_KEY: str = os.getenv("KIWI_API_KEY", "")
SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")

# Dashboard server
DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "5050"))
