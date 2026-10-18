"""LangGraph node implementations for the Paylane support agent.

Each function here is a self-contained graph node.  graph.py wires them
together into the StateGraph; it no longer contains any business logic.
"""

import re
from datetime import UTC, datetime
from textwrap import dedent

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from paylane.agent.guards import check_refund_eligibility
from paylane.agent.llm import create_chat_model
from paylane.agent.state import AgentState, Intent
from paylane.data.customers import get_customer as lookup_customer
from paylane.data.refunds import has_been_refunded
from paylane.data.refunds import issue_refund as record_refund
from paylane.data.tickets import escalate_to_human as create_ticket
from paylane.data.transactions import TEST_NOW
from paylane.data.transactions import get_transaction as lookup_transaction

# ---------------------------------------------------------------------------
# Private helpers: entity extraction & intent classification
# ---------------------------------------------------------------------------

def _extract_entities(text: str) -> dict:
    """Extract email, card last 4 digits, txn ID, and loss amounts from text."""
    entities: dict = {}

    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text
    )
    if email_match:
        entities["email"] = email_match.group(0).strip()

    txn_match = re.search(r"\btxn_\w+\b", text, re.IGNORECASE)
    if txn_match:
        entities["txn_id"] = txn_match.group(0).lower()

    card_match = re.search(
        r"(?:card(?:\s+ending\s+in|\s+last\s+4(?:\s+digits)?)?[:\s]+|[#\s]|^)(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if card_match:
        entities["card_last4"] = card_match.group(1)
    elif re.search(r"^\s*\d{4}\s*$", text):
        entities["card_last4"] = text.strip()

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

    # 6. General policy questions
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


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

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

    if "email" in entities:
        updates["supplied_email"] = entities["email"]
    if "card_last4" in entities:
        updates["supplied_card_last4"] = entities["card_last4"]
    if "txn_id" in entities:
        updates["transaction_id"] = entities["txn_id"]
    if "amount" in entities:
        updates["reported_loss_amount"] = entities["amount"]

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


def verify_customer(state: AgentState) -> dict:
    """Verify customer identity against mock customer records."""
    if state.get("verified"):
        return {}

    supplied_email = state.get("supplied_email")
    supplied_card_last4 = state.get("supplied_card_last4")

    if not supplied_email or not supplied_card_last4:
        return {"workflow_status": "awaiting_verification"}

    customer = lookup_customer(supplied_email)

    if customer is not None and customer.get("card_last4") == supplied_card_last4:
        updates: dict = {
            "verified": True,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "customer_status": customer["status"],
            "workflow_status": "in_progress",
        }
        if customer["status"] == "frozen":
            updates["handoff_required"] = True
            updates["intent"] = "frozen_card"
            updates["handoff_reason"] = (
                "Customer card is frozen. Escalating to human support for review."
            )
        return updates

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
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "customer_not_verified"}

    if not owns_txn or status == "not_found":
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "transaction_not_found"}

    if status == "refunded" or (txn_id and has_been_refunded(txn_id)):
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "already_refunded"}

    if status == "pending":
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "pending_transaction"}

    if status != "settled":
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "transaction_not_settled"}

    if amount is None or amount <= 0:
        return {"refund_eligible": False, "refund_id": None, "policy_reason": "invalid_amount"}

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

    txn_date_str = state.get("transaction_date_str")
    if txn_date_str:
        txn_date = datetime.fromisoformat(txn_date_str).astimezone(UTC)
        now = TEST_NOW.astimezone(UTC)
        age = now - txn_date

        if age.total_seconds() < 0:
            return {"refund_eligible": False, "refund_id": None, "policy_reason": "future_transaction_date"}

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


# ---------------------------------------------------------------------------
# LLM response node
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = dedent("""\
    You are Paylane's friendly AI support assistant. Your job is to help customers
    with their cards, transactions, and refunds.

    Tone guidelines:
    - Be warm, concise, and professional.
    - Never make promises that policy does not allow.
    - Do not reveal the customer's stored email address or full card number.
    - Keep responses short — 2-4 sentences unless more detail is genuinely needed.

    Policy rules you must follow:
    - Refunds are automatically approved for *settled* transactions ≤ $75.00 that are
      less than 30 days old.
    - Transactions > $75.00 or ≥ 30 days old require manual review (escalation).
    - Pending charges cannot be refunded until they settle.
    - A transaction can only be refunded once.
    - Customers must verify identity (email + last 4 card digits) before you access
      account details. After 3 failed attempts all account actions are blocked.
    - Fraud, legal threats, account closure, and frozen-card situations are always
      escalated to a human agent.

    You will receive a CONTEXT block that describes what has already happened in
    the workflow (verification status, policy outcome, escalation details, etc.).
    Use that context to craft an accurate, helpful response to the customer.
    Never invent transaction IDs, refund amounts, or ticket numbers — only use
    values provided in the context.
""")


def _build_context(state: AgentState) -> str:
    """Summarise the current workflow state into a plain-text context block."""
    lines: list[str] = []

    lines.append(f"Intent: {state.get('intent', 'unknown')}")

    verified = state.get("verified", False)
    lines.append(f"Customer verified: {verified}")
    if verified:
        lines.append(f"Customer name: {state.get('customer_name', 'unknown')}")

    attempts = state.get("verification_attempts", 0)
    if attempts:
        lines.append(f"Failed verification attempts: {attempts}")

    lines.append("Email: provided (do NOT reveal it)" if state.get("supplied_email") else "Email: not yet provided")
    lines.append("Card last-4: provided" if state.get("supplied_card_last4") else "Card last-4: not yet provided")

    if state.get("workflow_status"):
        lines.append(f"Workflow status: {state['workflow_status']}")

    if state.get("action_blocked") or state.get("actions_stopped"):
        lines.append("Account actions: BLOCKED")

    ticket_id = state.get("ticket_id")
    if ticket_id:
        lines.append(f"Escalation ticket ID: {ticket_id}")
        lines.append(f"Ticket priority: {state.get('ticket_priority', 'normal')}")
        lines.append(f"Escalation reason: {state.get('handoff_reason', '')}")

    if state.get("transaction_id"):
        lines.append(f"Transaction ID: {state['transaction_id']}")
    if state.get("transaction_status"):
        lines.append(f"Transaction status: {state['transaction_status']}")
    if state.get("transaction_amount") is not None:
        lines.append(f"Transaction amount: ${state['transaction_amount']:.2f}")
    if state.get("transaction_merchant"):
        lines.append(f"Merchant: {state['transaction_merchant']}")

    if state.get("policy_reason"):
        lines.append(f"Policy outcome: {state['policy_reason']}")

    refund_id = state.get("refund_id")
    if refund_id:
        lines.append(f"Refund confirmation ID: {refund_id}")
        lines.append(f"Refund amount: ${state.get('transaction_amount', 0.0):.2f}")

    if state.get("refund_eligible") is not None:
        lines.append(f"Refund eligible: {state['refund_eligible']}")

    return "\n".join(lines)


def compose_response_node(state: AgentState) -> dict:
    """Generate the final customer-facing response using the LLM."""
    context = _build_context(state)

    history = [
        msg for msg in state.get("messages", [])
        if isinstance(msg, (HumanMessage, AIMessage))
    ]

    system_msg = SystemMessage(
        content=(
            f"{_SYSTEM_PROMPT}\n\n"
            f"--- WORKFLOW CONTEXT ---\n{context}\n--- END CONTEXT ---"
        )
    )

    llm = create_chat_model()
    reply = llm.invoke([system_msg] + history)
    return {"messages": [reply]}


__all__ = [
    "answer_general_node",
    "check_safety_and_policy",
    "classify_request",
    "compose_response_node",
    "decide_refund",
    "escalate_node",
    "issue_refund_node",
    "lookup_transaction_node",
    "verify_customer",
]
