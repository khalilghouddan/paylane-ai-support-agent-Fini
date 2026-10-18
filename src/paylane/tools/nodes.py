"""LangGraph node implementations for the Paylane support agent.

Intent classification and entity extraction are delegated entirely to the
LLM (structured JSON response).  Deterministic policy/data nodes remain
for correctness and auditability.
"""

import json
import re
from datetime import UTC, datetime
from textwrap import dedent

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from paylane.agent.guards import check_refund_eligibility
from paylane.agent.llm import create_chat_model
from paylane.agent.state import AgentState
from paylane.data.customers import get_customer as lookup_customer
from paylane.data.refunds import has_been_refunded
from paylane.data.refunds import issue_refund as record_refund
from paylane.data.tickets import escalate_to_human as create_ticket
from paylane.data.transactions import TEST_NOW
from paylane.data.transactions import get_transaction as lookup_transaction

# ---------------------------------------------------------------------------
# Classifier node  —  LLM does intent + entity extraction in one call
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = dedent("""\
    You are a classifier for a fintech customer-support system called Paylane.

    From the customer message below, extract the following information and return
    it as a single, valid JSON object with exactly these keys:

    {
      "intent": "<one of: general_policy | refund | transaction_query | frozen_card |
                  suspected_fraud | legal_action | account_closure | human_request | unknown>",
      "email": "<email address found in the message, or null>",
      "card_last4": "<last 4 digits of the card found in the message, or null>",
      "txn_id": "<transaction ID like txn_001 found in the message, or null>",
      "amount": <dollar amount as a number if mentioned, or null>,
      "handoff_required": <true if the intent requires a human agent, otherwise false>,
      "handoff_reason": "<short reason if handoff_required is true, otherwise null>"
    }

    Intent rules:
    - "legal_action"    → customer mentions suing, lawyers, lawsuits, court, CFPB, arbitration, or legal action
    - "account_closure" → customer wants to close, delete, cancel, or shut down their account
    - "human_request"   → customer wants to speak with a human, agent, manager, or representative
    - "suspected_fraud" → customer reports fraud, unauthorized charge, stolen card, hacking, or scam
    - "frozen_card"     → customer mentions a frozen, blocked, or declined card
    - "general_policy"  → customer asks about refund policy, rules, or how refunds work (no specific transaction)
    - "refund"          → customer requests a refund for a specific transaction
    - "transaction_query" → customer asks about a specific transaction or charge
    - "unknown"         → none of the above

    Escalation rules (set handoff_required to true for):
    legal_action, account_closure, human_request, suspected_fraud

    Return ONLY the JSON object. No explanation, no markdown, no code fences.
""")


def classify_request(state: AgentState) -> dict:
    """Use the LLM to classify intent and extract entities from the last message."""
    messages = state.get("messages", [])
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    if not last_user_message:
        return {}

    llm = create_chat_model()
    response = llm.invoke([
        SystemMessage(content=_CLASSIFY_PROMPT),
        HumanMessage(content=last_user_message),
    ])

    data: dict = {}
    try:
        raw = response.content if isinstance(response.content, str) else str(response.content)
        raw = raw.strip()
        # Find JSON object boundaries in case LLM added conversational text or markdown
        start_idx = raw.find("{")
        end_idx = raw.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            raw = raw[start_idx : end_idx + 1]
        else:
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
        else:
            data = {"intent": "unknown"}
    except Exception:
        data = {"intent": "unknown"}

    updates: dict = {}

    email_val = data.get("email")
    if not email_val:
        m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", last_user_message)
        if m:
            email_val = m.group(0)

    card_val = data.get("card_last4")
    if not card_val:
        cleaned = re.sub(r"txn_\w+", "", last_user_message, flags=re.IGNORECASE)
        m = re.search(r"\b(\d{4})\b", cleaned)
        if m:
            card_val = m.group(1)

    txn_val = data.get("txn_id")
    if not txn_val:
        m = re.search(r"\b(txn_\d+)\b", last_user_message, flags=re.IGNORECASE)
        if m:
            txn_val = m.group(1)

    # Intent — persist previous non-trivial intent if the new one is unknown or general_policy
    intent = (data.get("intent") or "unknown") if isinstance(data, dict) else "unknown"
    previous = state.get("intent")
    if (intent in ("unknown", "general_policy") or email_val or card_val) and previous and previous not in ("unknown", "general_policy"):
        updates["intent"] = previous
        if email_val or card_val:
            data["handoff_required"] = False
    else:
        updates["intent"] = intent

    # Entities — only write if found
    if email_val:
        updates["supplied_email"] = str(email_val).strip()
    if card_val:
        updates["supplied_card_last4"] = str(card_val).strip()
    if txn_val:
        updates["transaction_id"] = str(txn_val).strip().lower()
    if data.get("amount") is not None:
        try:
            amt = float(data["amount"])
            updates["reported_loss_amount"] = amt
            # High-value fraud → escalate with high priority
            if intent == "suspected_fraud" and amt > 500:
                updates["ticket_priority"] = "high"
                data["handoff_reason"] = (
                    f"Suspected fraud with high reported loss (${amt:.2f} > $500)."
                )
            elif intent == "suspected_fraud":
                updates["ticket_priority"] = "normal"
        except (ValueError, TypeError):
            pass

    if data.get("handoff_required"):
        updates["handoff_required"] = True
        updates["handoff_reason"] = (
            data.get("handoff_reason")
            or "Customer inquiry requires human assistance."
        )

    return updates


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

def check_safety_and_policy(state: AgentState) -> dict:
    """Block further actions when the session has already been stopped."""
    return {"action_blocked": True} if state.get("actions_stopped") else {}


# ---------------------------------------------------------------------------
# Identity verification  (deterministic — must not be LLM-driven)
# ---------------------------------------------------------------------------

def verify_customer(state: AgentState) -> dict:
    """Verify customer identity against mock records (two-factor: email + card)."""
    if state.get("verified"):
        return {}

    email = state.get("supplied_email")
    card4 = state.get("supplied_card_last4")

    if not email or not card4:
        return {"workflow_status": "awaiting_verification"}

    customer = lookup_customer(email)
    if customer and customer.get("card_last4") == card4:
        updates: dict = {
            "verified": True,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "customer_status": customer["status"],
            "workflow_status": "in_progress",
        }
        if customer["status"] == "frozen":
            updates.update({
                "handoff_required": True,
                "intent": "frozen_card",
                "handoff_reason": "Customer card is frozen. Escalating to human support.",
            })
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
    return {"verified": False, "verification_attempts": attempts, "workflow_status": "awaiting_verification"}


# ---------------------------------------------------------------------------
# Transaction lookup
# ---------------------------------------------------------------------------

def lookup_transaction_node(state: AgentState) -> dict:
    """Look up a transaction belonging to the verified customer."""
    customer_id = state.get("customer_id")
    txn_id = state.get("transaction_id")

    if not customer_id or not txn_id:
        return {"transaction_status": "not_found", "refund_eligible": False, "policy_reason": "missing_transaction_context"}

    txn = lookup_transaction(customer_id, txn_id)
    if txn is None:
        return {"transaction_status": "not_found", "refund_eligible": False, "policy_reason": "transaction_not_found"}

    return {
        "transaction_amount": float(txn["amount"]),
        "transaction_status": txn["status"],
        "transaction_date_str": txn["date"],
        "transaction_merchant": txn.get("merchant"),
        "owns_transaction": True,
    }


# ---------------------------------------------------------------------------
# Refund policy decision  (deterministic — safety-critical)
# ---------------------------------------------------------------------------

def decide_refund(state: AgentState) -> dict:
    """Apply deterministic refund eligibility rules."""
    txn_id = state.get("transaction_id")
    status = state.get("transaction_status")
    amount = state.get("transaction_amount")
    verified = state.get("verified", False)
    owns_txn = state.get("owns_transaction", False)

    def deny(reason: str) -> dict:
        return {"refund_eligible": False, "refund_id": None, "policy_reason": reason}

    if not verified:
        return deny("customer_not_verified")
    if not owns_txn or status == "not_found":
        return deny("transaction_not_found")
    if status == "refunded" or (txn_id and has_been_refunded(txn_id)):
        return deny("already_refunded")
    if status == "pending":
        return deny("pending_transaction")
    if status != "settled":
        return deny("transaction_not_settled")
    if not amount or amount <= 0:
        return deny("invalid_amount")

    if amount > 75.00:
        return {**deny("amount_requires_escalation"), "handoff_required": True,
                "handoff_reason": f"Amount ${amount:.2f} exceeds the $75 automatic refund limit."}

    txn_date_str = state.get("transaction_date_str")
    if txn_date_str:
        age = TEST_NOW.astimezone(UTC) - datetime.fromisoformat(txn_date_str).astimezone(UTC)
        if age.total_seconds() < 0:
            return deny("future_transaction_date")
        if age.total_seconds() >= 30 * 24 * 3600:
            return {**deny("transaction_requires_escalation"), "handoff_required": True,
                    "handoff_reason": f"Transaction is {age.days} days old, exceeding the 30-day window."}

    eligible, reason = check_refund_eligibility(
        verified=verified, owns_transaction=owns_txn, amount=amount,
        transaction_date=datetime.fromisoformat(txn_date_str).astimezone(UTC) if txn_date_str else TEST_NOW,
        status=status, now=TEST_NOW,
    )
    return {"refund_eligible": True, "policy_reason": "eligible"} if eligible else deny(reason)


# ---------------------------------------------------------------------------
# Refund execution
# ---------------------------------------------------------------------------

def issue_refund_node(state: AgentState) -> dict:
    """Execute refund in the mock ledger."""
    txn_id, amount = state.get("transaction_id"), state.get("transaction_amount")
    if not txn_id or amount is None:
        return {"refund_eligible": False, "policy_reason": "missing_refund_parameters"}

    result = record_refund(txn_id, amount)
    if result.get("ok"):
        return {"refund_id": result["refund_id"], "workflow_status": "completed", "policy_reason": "refund_succeeded"}
    return {"refund_eligible": False, "policy_reason": result.get("reason", "refund_failed")}


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def escalate_node(state: AgentState) -> dict:
    """Create a human-support ticket."""
    summary = state.get("handoff_reason") or "Customer inquiry requires human assistance."
    priority = state.get("ticket_priority") or "normal"
    ticket = create_ticket(
        customer_id=state.get("customer_id"),
        summary=summary,
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
    """Mark general policy inquiry as ready for LLM response."""
    return {"workflow_status": "completed"}


# ---------------------------------------------------------------------------
# LLM response composer
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = dedent("""\
    You are Paylane's friendly AI support assistant helping customers with
    cards, transactions, and refunds.

    Guidelines:
    - Warm, concise, professional tone. 2-4 sentences max.
    - Never reveal the stored email or full card number.
    - Never promise anything outside policy.

    Policy:
    - Auto-refund: settled transactions ≤ $75, less than 30 days old.
    - Transactions > $75 or ≥ 30 days → manual review (escalation).
    - Pending charges cannot be refunded until settled.
    - Each transaction can only be refunded once.
    - Identity verification requires email + last 4 card digits.
      After 3 failed attempts, all account actions are blocked.
    - Fraud, legal threats, account closure, and frozen cards → always escalated.

    A CONTEXT block below describes the current workflow state.
    Use only the values in it — never invent IDs, amounts, or ticket numbers.
""")


def _build_context(state: AgentState) -> str:
    parts = [
        f"Intent: {state.get('intent') or 'unknown'}",
        f"Customer verified: {state.get('verified', False)}",
    ]
    if state.get("verified"):
        parts.append(f"Customer name: {state.get('customer_name', 'unknown')}")
    if state.get("verification_attempts"):
        parts.append(f"Failed verification attempts: {state['verification_attempts']}")
    parts.append("Email: provided (do NOT reveal)" if state.get("supplied_email") else "Email: not provided")
    parts.append("Card last-4: provided" if state.get("supplied_card_last4") else "Card last-4: not provided")
    if state.get("workflow_status"):
        parts.append(f"Workflow status: {state['workflow_status']}")
    if state.get("action_blocked") or state.get("actions_stopped"):
        parts.append("Account actions: BLOCKED")
    if state.get("ticket_id"):
        parts += [
            f"Escalation ticket ID: {state['ticket_id']}",
            f"Ticket priority: {state.get('ticket_priority', 'normal')}",
            f"Escalation reason: {state.get('handoff_reason', '')}",
        ]
    for key, label in [
        ("transaction_id", "Transaction ID"),
        ("transaction_status", "Transaction status"),
        ("transaction_merchant", "Merchant"),
        ("policy_reason", "Policy outcome"),
        ("refund_id", "Refund confirmation ID"),
    ]:
        if state.get(key):
            parts.append(f"{label}: {state[key]}")
    if state.get("transaction_amount") is not None:
        parts.append(f"Transaction amount: ${state['transaction_amount']:.2f}")
    if state.get("refund_eligible") is not None:
        parts.append(f"Refund eligible: {state['refund_eligible']}")
    return "\n".join(parts)


def compose_response_node(state: AgentState) -> dict:
    """Generate the final customer-facing response using the LLM."""
    context = _build_context(state)
    history = [m for m in state.get("messages", []) if isinstance(m, (HumanMessage, AIMessage))]
    system_msg = SystemMessage(
        content=f"{_SYSTEM_PROMPT}\n\n--- WORKFLOW CONTEXT ---\n{context}\n--- END CONTEXT ---"
    )
    reply = create_chat_model().invoke([system_msg] + history)
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
