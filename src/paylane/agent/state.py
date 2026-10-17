"""Agent conversation state.

Defines the shared LangGraph state shape and tracked workflow metadata.
"""

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Intent = Literal[
    "general_policy",
    "account_query",
    "transaction_query",
    "refund",
    "frozen_card",
    "suspected_fraud",
    "legal_action",
    "account_closure",
    "human_request",
    "unknown",
]

WorkflowStatus = Literal[
    "in_progress",
    "awaiting_verification",
    "awaiting_transaction_id",
    "refund_pending",
    "completed",
    "escalated",
    "blocked",
]


class AgentState(TypedDict):
    """Conversation state and trusted workflow metadata."""

    # Conversation history
    messages: Annotated[list[BaseMessage], add_messages]

    # Request classification
    intent: NotRequired[Intent]
    workflow_status: NotRequired[WorkflowStatus]

    # Trusted session identity; never set these from an LLM response
    supplied_email: NotRequired[str | None]
    supplied_card_last4: NotRequired[str | None]
    customer_id: NotRequired[str | None]
    customer_name: NotRequired[str | None]
    customer_status: NotRequired[str | None]
    verified: NotRequired[bool]
    verification_attempts: NotRequired[int]

    # Transaction context
    transaction_id: NotRequired[str | None]
    transaction_amount: NotRequired[float | None]
    transaction_status: NotRequired[str | None]
    transaction_age_days: NotRequired[float | None]
    transaction_date_str: NotRequired[str | None]
    transaction_merchant: NotRequired[str | None]
    owns_transaction: NotRequired[bool]

    # Policy decision
    refund_eligible: NotRequired[bool]
    policy_reason: NotRequired[str | None]
    refund_id: NotRequired[str | None]

    # Human handoff
    handoff_required: NotRequired[bool]
    handoff_reason: NotRequired[str | None]
    ticket_id: NotRequired[str | None]
    ticket_priority: NotRequired[str | None]
    reported_loss_amount: NotRequired[float | None]

    # Workflow control
    action_blocked: NotRequired[bool]
    actions_stopped: NotRequired[bool]


# Alias for backward compatibility
SupportState = AgentState

__all__ = ["AgentState", "Intent", "SupportState", "WorkflowStatus"]
