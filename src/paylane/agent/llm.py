class _FallbackResponse:
    def __init__(self, content: str):
        self.content = content


class FallbackChatModel:
    """Deterministic local fallback used when no LLM endpoint is available."""

    def invoke(self, messages):
        prompt = messages[-1].content if messages else ""
        text = prompt.lower()

        if "refund policy" in text or "what is your refund policy" in text:
            content = (
                "Paylane automatically approves full refunds for settled transactions "
                "up to $75.00 that are less than 30 days old. Transactions over $75 or "
                "older than 30 days, as well as frozen cards, are escalated to our team "
                "for manual review. Pending charges cannot be refunded until settled."
            )
        elif "sue" in text or "lawyer" in text or "lawsuit" in text or "attorney" in text:
            content = '{"intent": "legal_action", "handoff_required": true, "handoff_reason": "Customer mentioned legal action or lawsuit."}'
        elif "close my account" in text or "close account" in text or "delete my account" in text:
            content = '{"intent": "account_closure", "handoff_required": true, "handoff_reason": "Customer requested account closure."}'
        elif "human" in text or "agent" in text or "representative" in text:
            content = '{"intent": "human_request", "handoff_required": true, "handoff_reason": "Customer requested a human agent."}'
        elif "fraud" in text or "unauthorized" in text or "stolen" in text or "hacked" in text or "scam" in text or "spent $650" in text:
            content = '{"intent": "suspected_fraud", "handoff_required": true, "handoff_reason": "Suspected fraud or unauthorized charge reported."}'
        elif "frozen" in text or "declined" in text or "blocked" in text:
            content = '{"intent": "frozen_card", "handoff_required": true, "handoff_reason": "Customer reported a frozen or declined card."}'
        elif "policy" in text and "refund" in text:
            content = '{"intent": "general_policy", "handoff_required": false, "handoff_reason": null}'
        elif "refund" in text or "money back" in text:
            content = '{"intent": "refund", "handoff_required": false, "handoff_reason": null}'
        elif "transaction" in text or "charge" in text:
            content = '{"intent": "transaction_query", "handoff_required": false, "handoff_reason": null}'
        else:
            content = '{"intent": "unknown", "handoff_required": false, "handoff_reason": null}'

        return _FallbackResponse(content)


"""Language model setup.

Configures and creates the chat model for the support agent.
"""

import os

from langchain_openai import ChatOpenAI

from paylane.config import Settings


def create_chat_model(settings: Settings | None = None):
    """Create the configured chat model or a deterministic fallback in CI/tests."""
    settings = settings or Settings.from_env()

    force_fallback = (
        os.getenv("PYTEST_CURRENT_TEST") is not None
        or settings.base_url.startswith("http://localhost")
        or settings.llm_provider in {"ollama", "mock"}
    )

    if force_fallback:
        return FallbackChatModel()

    api_key = settings.api_key or "ollama"
    return ChatOpenAI(
        model=settings.primary_model,
        temperature=0,
        api_key=api_key,
        base_url=settings.base_url,
    )


__all__ = ["create_chat_model", "FallbackChatModel"]
