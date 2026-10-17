"""Paylane Support Agent LangGraph workflow.

Implements the multi-step graph with deterministic policy checks,
entity extraction, two-factor customer verification, refund policy evaluation,
and human escalation.
"""

import re
from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from paylane.agent.guards import check_refund_eligibility
from paylane.agent.state import AgentState, Intent, SupportState
from paylane.data.customers import get_customer as lookup_customer
from paylane.data.refunds import (
    has_been_refunded,
)
from paylane.data.refunds import (
    issue_refund as record_refund,
)
from paylane.data.tickets import (
    escalate_to_human as create_ticket,
)
from paylane.data.transactions import (
    TEST_NOW,
)
from paylane.data.transactions import (
    get_transaction as lookup_transaction,
)


def _extract_entities(text: str) -> dict:
    """Extract email, card last 4 digits, txn ID, and loss amounts from text."""
    entities: dict = {}

    # Email extraction
    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text
    )
    if email_match:
        entities["email"] = email_match.group(0).strip()

    # Transaction ID extraction (e.g., txn_001)
    txn_match = re.search(r"\btxn_\w+\b", text, re.IGNORECASE)
    if txn_match:
        entities["txn_id"] = txn_match.group(0).lower()

    # Card last 4 extraction: "card ending in 4242", "last 4 digits are 4242", or 4 digits
    card_match = re.search(
        r"(?:card(?:\s+ending\s+in|\s+last\s+4(?:\s+digits)?)?[:\s]+|[#\s]|^)(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if card_match:
        entities["card_last4"] = card_match.group(1)
    elif re.search(r"^\s*\d{4}\s*$", text):
        entities["card_last4"] = text.strip()

    # Dollar amounts for loss reports
    amount_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", text)
    if amount_match:
        entities["amount"] = float(amount_match.group(1))
    else:
        num_match = re.search(
            r"\b([0-9]+(?:\.[0-9]{2})?)\s*(?:dollars|usd)\b", text, re.IGNORECASE
        )
        if num_match:
            entities["amount"] = float(num_match.group(1))

    return entities


def _classify_intent(text: str) -> tuple[Intent, dict]:
    """Classify the user intent and detect critical escalation triggers."""
    text_lower = text.lower()
    details: dict = {}

    # 1. Legal action / threats
    if (
        re.search(
            r"\b(?:sue|suing|lawyer|attorney|lawsuit|court|cfpb|arbitration)\b",
            text_lower,
        )
        or "legal action" in text_lower
        or "take you to court" in text_lower
    ):
        details["handoff_required"] = True
        details["handoff_reason"] = "Customer mentioned legal action or lawsuit."
        return "legal_action", details

    # 2. Account closure
    if any(
        kw in text_lower
        for kw in (
            "close my account",
            "close account",
            "delete my account",
            "delete account",
            "cancel my account",
            "shut down my account",
        )
    ):
        details["handoff_required"] = True
        details["handoff_reason"] = "Customer requested account closure."
        return "account_closure", details

    # 3. Explicit human request
    if any(
        kw in text_lower
        for kw in (
            "speak to a human",
            "talk to a human",
            "speak to a person",
            "talk to a person",
            "human agent",
            "real person",
            "customer service agent",
            "representative",
            "speak with someone",
            "human support",
            "speak to someone",
            "talk to someone",
            "agent",
            "manager",
        )
    ):
        details["handoff_required"] = True
        details["handoff_reason"] = (
            "Customer explicitly requested to speak with a human."
        )
        return "human_request", details

    # 4. Suspected fraud / unauthorized charges
    if any(
        kw in text_lower
        for kw in (
            "fraud",
            "unauthorized",
            "stolen card",
            "card stolen",
            "hacked",
            "scam",
            "didn't authorize",
            "did not authorize",
            "suspicious charge",
            "unrecognized charge",
        )
    ):
        details["handoff_required"] = True
        details["handoff_reason"] = (
            "Customer reported suspected fraud or unauthorized activity."
        )
        return "suspected_fraud", details

    # 5. Frozen card
    if any(
        kw in text_lower
        for kw in (
            "frozen",
            "card is frozen",
            "unfreeze",
            "card blocked",
            "blocked card",
            "freeze",
            "declined",
            "card declined",
            "card was declined",
            "card not working",
        )
    ):
        return "frozen_card", details

    # 6. General policy questions (must precede specific refund/transaction checks)
    if any(
        kw in text_lower
        for kw in (
            "how do refunds work",
            "what is your refund policy",
            "refund policy",
            "policy on refunds",
            "policy for refunds",
            "how long do refunds take",
            "what are the rules",
            "general question",
            "rules for refund",
            "can you explain the refund policy",
            "policy",
        )
    ):
        return "general_policy", details

    # 7. Refund requests
    if any(
        kw in text_lower
        for kw in (
            "refund",
            "money back",
            "return my money",
            "reimburse",
            "dispute this charge",
            "cancel payment",
        )
    ):
        return "refund", details

    # 8. Transaction query
    if any(
        kw in text_lower for kw in ("transaction", "charge", "txn_", "payment details")
    ):
        return "transaction_query", details

    return "unknown", details


def classify_request(state: AgentState) -> dict:
    """Classify the user intent and extract relevant entities from messages."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = (
                msg.content if isinstance(msg.content, str) else str(msg.content)
            )
            break

    intent, details = _classify_intent(last_user_message)
    entities = _extract_entities(last_user_message)

    previous_intent = state.get("intent")
    if (
        intent == "unknown"
        and previous_intent
        and previous_intent not in ("unknown", "general_policy")
    ):
        updates: dict = {"intent": previous_intent}
    else:
        updates: dict = {"intent": intent}

    # Entity persistence
    if "email" in entities:
        updates["supplied_email"] = entities["email"]
    if "card_last4" in entities:
        updates["supplied_card_last4"] = entities["card_last4"]
    if "txn_id" in entities:
        updates["transaction_id"] = entities["txn_id"]
    if "amount" in entities:
        updates["reported_loss_amount"] = entities["amount"]

    # Escalation priority for fraud
    if intent == "suspected_fraud":
        loss = entities.get("amount") or state.get("reported_loss_amount") or 0.0
        if loss > 500:
            updates["ticket_priority"] = "high"
            details["handoff_reason"] = (
                f"Suspected fraud with high reported loss (${loss:.2f} > $500)."
            )
        else:
            updates["ticket_priority"] = "normal"

    if details.get("handoff_required"):
        updates["handoff_required"] = True
        updates["handoff_reason"] = details.get("handoff_reason")

    return updates


def check_safety_and_policy(state: AgentState) -> dict:
    """Evaluate session safety rules and enforce stopping conditions."""
    if state.get("actions_stopped"):
        return {"action_blocked": True}

    return {}


def route_request(
    state: AgentState,
) -> Literal[
    "escalate", "answer_general", "verify", "lookup_transaction", "compose_response"
]:
    """Route the request based on safety, verification, and intent."""
    if state.get("actions_stopped"):
        return "compose_response"

    if state.get("handoff_required"):
        return "escalate"

    if state.get("intent") == "general_policy":
        return "answer_general"

    if not state.get("verified"):
        return "verify"

    # Verified customer workflows
    if state.get("intent") == "frozen_card":
        if state.get("customer_status") == "frozen":
            return "escalate"
        return "compose_response"

    if state.get("intent") in ("refund", "transaction_query"):
        if state.get("transaction_id"):
            return "lookup_transaction"
        return "compose_response"

    return "compose_response"


def verify_customer(state: AgentState) -> dict:
    """Verify customer identity against mock customer records."""
    if state.get("verified"):
        return {}

    supplied_email = state.get("supplied_email")
    supplied_card_last4 = state.get("supplied_card_last4")

    # If either piece of info is missing, await customer input without counting failure
    if not supplied_email or not supplied_card_last4:
        return {"workflow_status": "awaiting_verification"}

    customer = lookup_customer(supplied_email)

    if customer is not None and customer.get("card_last4") == supplied_card_last4:
        # Verification succeeded!
        updates: dict = {
            "verified": True,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "customer_status": customer["status"],
            "workflow_status": "in_progress",
        }
        # If card is frozen, trigger escalation
        if customer["status"] == "frozen":
            updates["handoff_required"] = True
            updates["intent"] = "frozen_card"
            updates["handoff_reason"] = (
                "Customer card is frozen. Escalating to human support for review."
            )
        return updates

    # Verification failed
    attempts = state.get("verification_attempts", 0) + 1
    if attempts >= 3:
        return {
            "verified": False,
            "verification_attempts": attempts,
            "handoff_required": True,
            "handoff_reason": "Exceeded 3 failed customer verification attempts.",
            "actions_stopped": True,
            "workflow_status": "blocked",
        }

    return {
        "verified": False,
        "verification_attempts": attempts,
        "workflow_status": "awaiting_verification",
    }


def route_after_verify(
    state: AgentState,
) -> Literal["escalate", "lookup_transaction", "compose_response"]:
    """Route after customer verification step."""
    if state.get("handoff_required"):
        return "escalate"

    if (
        state.get("verified")
        and state.get("intent") in ("refund", "transaction_query")
        and state.get("transaction_id")
    ):
        return "lookup_transaction"

    return "compose_response"


def lookup_transaction_node(state: AgentState) -> dict:
    """Look up a transaction belonging to the verified customer."""
    customer_id = state.get("customer_id")
    txn_id = state.get("transaction_id")

    if not customer_id or not txn_id:
        return {
            "transaction_status": "not_found",
            "refund_eligible": False,
            "policy_reason": "missing_transaction_context",
        }

    transaction = lookup_transaction(customer_id, txn_id)

    if transaction is None:
        return {
            "transaction_status": "not_found",
            "refund_eligible": False,
            "policy_reason": "transaction_not_found",
        }

    return {
        "transaction_amount": float(transaction["amount"]),
        "transaction_status": transaction["status"],
        "transaction_date_str": transaction["date"],
        "transaction_merchant": transaction.get("merchant"),
        "owns_transaction": True,
    }


def decide_refund(state: AgentState) -> dict:
    """Evaluate deterministic refund policy rules."""
    txn_id = state.get("transaction_id")
    status = state.get("transaction_status")
    amount = state.get("transaction_amount")
    verified = state.get("verified", False)
    owns_txn = state.get("owns_transaction", False)

    if not verified:
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "customer_not_verified",
        }

    if not owns_txn or status == "not_found":
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "transaction_not_found",
        }

    if status == "refunded" or (txn_id and has_been_refunded(txn_id)):
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "already_refunded",
        }

    if status == "pending":
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "pending_transaction",
        }

    if status != "settled":
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "transaction_not_settled",
        }

    if amount is None or amount <= 0:
        return {
            "refund_eligible": False,
            "refund_id": None,
            "policy_reason": "invalid_amount",
        }

    # Refund Amount Rule: <= $75.00 automatically, > $75.00 must escalate
    if amount > 75.00:
        return {
            "refund_eligible": False,
            "refund_id": None,
            "handoff_required": True,
            "handoff_reason": (
                f"Transaction amount ${amount:.2f} exceeds automatic refund limit ($75.00)."
            ),
            "policy_reason": "amount_requires_escalation",
        }

    # Refund Age Rule: strictly less than 30 elapsed days in UTC
    txn_date_str = state.get("transaction_date_str")
    if txn_date_str:
        txn_date = datetime.fromisoformat(txn_date_str).astimezone(UTC)
        now = TEST_NOW.astimezone(UTC)
        age = now - txn_date

        if age.total_seconds() < 0:
            return {
                "refund_eligible": False,
                "refund_id": None,
                "policy_reason": "future_transaction_date",
            }

        if age.total_seconds() >= 30 * 24 * 60 * 60:
            return {
                "refund_eligible": False,
                "refund_id": None,
                "handoff_required": True,
                "handoff_reason": (
                    f"Transaction is {age.days} days old, exceeding 30-day automatic refund window."
                ),
                "policy_reason": "transaction_requires_escalation",
            }

    # Deterministic double check with guards
    eligible, reason = check_refund_eligibility(
        verified=verified,
        owns_transaction=owns_txn,
        amount=amount,
        transaction_date=datetime.fromisoformat(txn_date_str).astimezone(UTC)
        if txn_date_str
        else TEST_NOW,
        status=status,
        now=TEST_NOW,
    )

    if not eligible:
        return {"refund_eligible": False, "refund_id": None, "policy_reason": reason}

    return {"refund_eligible": True, "policy_reason": "eligible"}


def route_refund(
    state: AgentState,
) -> Literal["issue_refund", "escalate", "compose_response"]:
    """Route based on deterministic refund decision."""
    if state.get("handoff_required"):
        return "escalate"

    if state.get("refund_eligible"):
        return "issue_refund"

    return "compose_response"


def issue_refund_node(state: AgentState) -> dict:
    """Execute refund in the mock ledger."""
    txn_id = state.get("transaction_id")
    amount = state.get("transaction_amount")

    if not txn_id or amount is None:
        return {"refund_eligible": False, "policy_reason": "missing_refund_parameters"}

    result = record_refund(txn_id, amount)
    if result.get("ok"):
        return {
            "refund_id": result["refund_id"],
            "workflow_status": "completed",
            "policy_reason": "refund_succeeded",
        }

    return {
        "refund_eligible": False,
        "policy_reason": result.get("reason", "refund_failed"),
    }


def escalate_node(state: AgentState) -> dict:
    """Escalate to a human support ticket."""
    customer_id = state.get("customer_id")
    reason = state.get("handoff_reason", "Customer inquiry requires human assistance.")
    priority = state.get("ticket_priority", "normal")

    ticket = create_ticket(
        customer_id=customer_id,
        summary=reason,
        priority=priority,
    )

    return {
        "ticket_id": ticket["ticket_id"],
        "ticket_priority": priority,
        "workflow_status": "escalated",
        "actions_stopped": True,
        "handoff_required": True,
    }


def answer_general_node(state: AgentState) -> dict:
    """Handle general policy inquiries without requiring verification."""
    return {"workflow_status": "completed"}


def compose_response_node(state: AgentState) -> dict:
    """Generate final customer-facing response following tone and safety rules."""
    response_text = ""

    # Check if actions were previously stopped
    if state.get("action_blocked") and state.get("ticket_id"):
        ticket_id = state.get("ticket_id")
        response_text = (
            f"Your request has already been escalated to our human support team under "
            f"ticket #{ticket_id}. A representative will follow up with you as soon as possible."
        )
        return {"messages": [AIMessage(content=response_text)]}

    # Newly escalated issues
    if state.get("ticket_id") and state.get("workflow_status") == "escalated":
        ticket_id = state.get("ticket_id")
        intent = state.get("intent")
        priority = state.get("ticket_priority", "normal")

        if intent == "legal_action":
            response_text = (
                f"I understand your concern. Due to the legal nature of your inquiry, I have "
                f"escalated your case directly to our senior support team (Ticket: {ticket_id}). "
                f"A specialist will review your file and respond to you."
            )
        elif intent == "account_closure":
            response_text = (
                f"I can certainly help you get that started. I've created a request with our "
                f"account management team (Ticket: {ticket_id}) to assist you with closing "
                f"your account safely."
            )
        elif intent == "human_request":
            response_text = (
                f"I've transferred your conversation to our human support team (Ticket: {ticket_id}). "
                f"A team member will be with you shortly."
            )
        elif intent == "suspected_fraud":
            priority_note = " with high priority" if priority == "high" else ""
            response_text = (
                f"Thank you for reporting this. I take security very seriously and have escalated "
                f"this incident to our fraud protection team{priority_note} (Ticket: {ticket_id}). "
                f"Our security specialists will investigate immediately."
            )
        elif intent == "frozen_card":
            response_text = (
                f"Your card is currently frozen. To ensure your account is protected, I have "
                f"escalated your case to our card security team (Ticket: {ticket_id}) for review. "
                f"They will reach out with the next steps."
            )
        elif state.get("verification_attempts", 0) >= 3:
            response_text = (
                f"For your security, you have exceeded the maximum of 3 verification attempts. "
                f"Account actions have been stopped and your case has been escalated to our "
                f"human support team (Ticket: {ticket_id})."
            )
        elif state.get("policy_reason") == "amount_requires_escalation":
            amount = state.get("transaction_amount", 0.0)
            response_text = (
                f"Transactions exceeding our automatic refund limit of $75.00 require human review. "
                f"I have escalated your refund request for ${amount:.2f} to our support team "
                f"(Ticket: {ticket_id})."
            )
        elif state.get("policy_reason") == "transaction_requires_escalation":
            response_text = (
                f"This transaction is 30 days old or older and cannot be refunded automatically. "
                f"I have forwarded your request to our support specialists for manual review "
                f"(Ticket: {ticket_id})."
            )
        else:
            response_text = (
                f"I have referred your request to our human support team (Ticket: {ticket_id}). "
                f"A representative will review your inquiry shortly."
            )
        return {"messages": [AIMessage(content=response_text)]}

    # Policy denials
    policy_reason = state.get("policy_reason")
    if policy_reason == "pending_transaction":
        txn_id = state.get("transaction_id")
        response_text = (
            f"Transaction {txn_id} is currently pending. Only settled transactions can be refunded. "
            f"Please check back once the charge has posted to your account."
        )
        return {"messages": [AIMessage(content=response_text)]}

    if policy_reason == "already_refunded":
        txn_id = state.get("transaction_id")
        response_text = (
            f"Transaction {txn_id} has already been refunded. We cannot issue duplicate refunds "
            f"for the same transaction."
        )
        return {"messages": [AIMessage(content=response_text)]}

    if policy_reason == "transaction_not_found":
        txn_id = state.get("transaction_id")
        response_text = (
            f"We could not find transaction {txn_id} associated with your account. "
            f"Please verify the transaction ID and try again."
        )
        return {"messages": [AIMessage(content=response_text)]}

    # Refund execution success
    if state.get("refund_id") and state.get("workflow_status") == "completed":
        refund_id = state.get("refund_id")
        amount = state.get("transaction_amount", 0.0)
        txn_id = state.get("transaction_id")
        response_text = (
            f"Your refund of ${amount:.2f} for transaction {txn_id} has been processed "
            f"successfully. Your refund confirmation number is {refund_id}."
        )
        return {"messages": [AIMessage(content=response_text)]}

    # General policy response (unauthenticated)
    if state.get("intent") == "general_policy":
        response_text = (
            "Paylane automatically approves full refunds for settled transactions up to $75.00 "
            "that are less than 30 days old. Transactions over $75 or older than 30 days, as well "
            "as frozen cards, are escalated to our team for manual review. Pending charges cannot "
            "be refunded until settled."
        )
        return {"messages": [AIMessage(content=response_text)]}

    # Verification state
    if not state.get("verified"):
        attempts = state.get("verification_attempts", 0)
        supplied_email = state.get("supplied_email")
        supplied_card = state.get("supplied_card_last4")

        if not supplied_email and not supplied_card:
            response_text = (
                "To access your account details and assist you, please provide the email address "
                "on your account and the last 4 digits of your card."
            )
        elif supplied_email and not supplied_card:
            response_text = "Thank you! Please also provide the last 4 digits of your card to complete verification."
        elif not supplied_email and supplied_card:
            response_text = "Thank you! Please also provide the email address associated with your Paylane account."
        else:
            remaining = 3 - attempts
            response_text = (
                f"The verification details provided did not match our records. You have "
                f"{remaining} attempt(s) remaining. Please double-check your email and the "
                f"last 4 digits of your card."
            )
        return {"messages": [AIMessage(content=response_text)]}

    # Verified but missing transaction ID
    if state.get("verified") and not state.get("transaction_id"):
        response_text = (
            "Your identity has been verified. Please provide the transaction ID (e.g., txn_001) "
            "you need assistance with."
        )
        return {"messages": [AIMessage(content=response_text)]}

    # Fallback
    response_text = (
        "Hello! I am Paylane's customer support assistant. How can I help you today with your "
        "cards, transactions, or refunds?"
    )
    return {"messages": [AIMessage(content=response_text)]}


def build_agent() -> StateGraph:
    """Build and compile the Paylane support agent LangGraph workflow."""
    builder = StateGraph(AgentState)

    builder.add_node("classify_request", classify_request)
    builder.add_node("check_safety_and_policy", check_safety_and_policy)
    builder.add_node("verify", verify_customer)
    builder.add_node("lookup_transaction", lookup_transaction_node)
    builder.add_node("decide_refund", decide_refund)
    builder.add_node("issue_refund", issue_refund_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("answer_general", answer_general_node)
    builder.add_node("compose_response", compose_response_node)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "check_safety_and_policy")

    builder.add_conditional_edges(
        "check_safety_and_policy",
        route_request,
    )

    builder.add_conditional_edges(
        "verify",
        route_after_verify,
    )

    builder.add_edge("lookup_transaction", "decide_refund")

    builder.add_conditional_edges(
        "decide_refund",
        route_refund,
    )

    builder.add_edge("issue_refund", "compose_response")
    builder.add_edge("escalate", "compose_response")
    builder.add_edge("answer_general", "compose_response")
    builder.add_edge("compose_response", END)

    return builder.compile()


support_graph = build_agent()

__all__ = [
    "AgentState",
    "SupportState",
    "answer_general_node",
    "build_agent",
    "check_safety_and_policy",
    "classify_request",
    "compose_response_node",
    "decide_refund",
    "escalate_node",
    "issue_refund_node",
    "lookup_transaction_node",
    "route_after_verify",
    "route_refund",
    "route_request",
    "support_graph",
    "verify_customer",
]
