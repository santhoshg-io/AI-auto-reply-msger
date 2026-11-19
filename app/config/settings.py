"""Application Settings & Configuration Management.

Uses Pydantic Settings for strictly typed, environment-driven configuration.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for AI Email Agent."""

    # AI Provider (Defaults to Groq)
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Fallback / OpenAI Settings if needed
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Agent Owner Persona & Preferences
    USER_NAME: str = "Santhosh"
    USER_ROLE: str = "Software Engineer & AI Researcher"
    DEFAULT_REPLY_TONE: Literal["formal", "professional", "friendly", "concise"] = "professional"

    # Decision & Automation Controls
    MIN_CONFIDENCE_THRESHOLD: float = 0.75
    AUTO_REPLY_ENABLED: bool = True  # Automatically reply when email is received & verified safe
    DAILY_AUTO_REPLY_LIMIT: int = 50
    POLL_INTERVAL_SECONDS: int = 60

    # Gmail OAuth2 File Paths
    GMAIL_CREDENTIALS_FILE: str = "credentials.json"
    GMAIL_TOKEN_FILE: str = "token.json"

    # Persistence
    DATABASE_URL: str = "sqlite:///./email_agent.db"
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
