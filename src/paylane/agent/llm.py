"""Language model setup.

Configures and creates the chat model for the support agent.
"""

from langchain_openai import ChatOpenAI

from paylane.config import Settings


def create_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """Create the configured chat model."""
    settings = settings or Settings.from_env()

    api_key = settings.api_key or "ollama"

    return ChatOpenAI(
        model=settings.primary_model,
        temperature=0,
        api_key=api_key,
        base_url=settings.base_url,
    )


__all__ = ["create_chat_model"]
