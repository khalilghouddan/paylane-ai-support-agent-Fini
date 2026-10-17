"""Application configuration.

Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Settings loaded from environment variables."""

    app_name: str = "Paylane Support Agent"
    llm_provider: str = "ollama"
    primary_model: str = "llama3.2:3b"
    fallback_model: str = "gemma3:1b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str | None = "ollama"

    @property
    def openai_api_key(self) -> str | None:
        return self.api_key

    @property
    def model_name(self) -> str:
        return self.primary_model

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings using environment variables."""
        return cls(
            app_name=os.getenv("APP_NAME", "Paylane Support Agent"),
            llm_provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
            primary_model=os.getenv(
                "OPENAI_MODEL", os.getenv("LLM_PRIMARY_MODEL", "llama3.2:3b")
            ),
            fallback_model=os.getenv("LLM_FALLBACK_MODEL", "gemma3:1b"),
            base_url=os.getenv(
                "OPENAI_BASE_URL",
                os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            ),
            api_key=os.getenv("OPENAI_API_KEY", os.getenv("LLM_API_KEY", "ollama")),
        )


settings = Settings.from_env()

__all__ = ["Settings", "settings"]
