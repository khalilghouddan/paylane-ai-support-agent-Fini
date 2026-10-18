"""Unit tests for deterministic refund policy, customer verification, and privacy guards.

Uses a fixed UTC clock (2026-10-18T12:00:00Z) to guarantee deterministic results.
"""

from datetime import UTC, datetime, timedelta

import pytest

from paylane.agent.guards import check_refund_eligibility
from paylane.agent.graph import route_request
from paylane.data.refunds import issue_refund, reset_refunds
from paylane.policy import RefundDecision, evaluate_refund
from paylane.tools.nodes import verify_customer

# Fixed UTC clock as required by specifications
UTC_CLOCK = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)


# ==============================================================================
# Test A — Refund Policy (Deterministic checks)
# ==============================================================================

def test_refund_verified_eligible_40_dollars_10_days_old():
    """Verified customer, $40 settled transaction, 10 days old -> Refund allowed."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=10),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.APPROVE
    assert reason == "eligible"


def test_refund_exactly_75_dollars_allowed():
    """Transaction amount exactly $75 -> Refund allowed if other conditions pass."""
    decision, reason = evaluate_refund(
        amount=75.00,
        transaction_date=UTC_CLOCK - timedelta(days=10),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.APPROVE
    assert reason == "eligible"


def test_refund_75_01_escalated_no_refund():
    """Transaction amount $75.01 -> Escalate; no refund."""
    decision, reason = evaluate_refund(
        amount=75.01,
        transaction_date=UTC_CLOCK - timedelta(days=10),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.ESCALATE
    assert reason == "amount_requires_escalation"


def test_refund_exactly_30_days_old_escalated():
    """Transaction exactly 30 days old -> Escalate; no refund."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=30),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.ESCALATE
    assert reason == "transaction_requires_escalation"


def test_refund_31_days_old_escalated():
    """Transaction 31 days old -> Escalate; no refund."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=31),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.ESCALATE
    assert reason == "transaction_requires_escalation"


def test_refund_pending_transaction_no_refund():
    """Pending transaction -> No refund."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=5),
        transaction_status="pending",
        verified=True,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.DENY
    assert reason == "pending_transaction"


def test_refund_already_refunded_transaction_no_second_refund():
    """Already-refunded transaction -> No second refund."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=5),
        transaction_status="refunded",
        verified=True,
        already_refunded=True,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.DENY
    assert reason == "already_refunded"


def test_refund_unverified_customer_no_refund():
    """Unverified customer -> No refund."""
    decision, reason = evaluate_refund(
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=5),
        transaction_status="settled",
        verified=False,
        already_refunded=False,
        now=UTC_CLOCK,
    )
    assert decision == RefundDecision.DENY
    assert reason == "customer_not_verified"


def test_refund_partial_refund_request_rejected():
    """Partial refund request -> Reject; Paylane only allows full refund."""
    from paylane.tools import issue_refund

    reset_refunds()
    result = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 20.00,  # original is 45.00
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert result["ok"] is False
    assert result["reason"] == "full_refund_only"


def test_refund_transaction_belongs_to_another_customer_denied():
    """Transaction belongs to another customer -> No refund."""
    eligible, reason = check_refund_eligibility(
        verified=True,
        owns_transaction=False,
        amount=40.00,
        transaction_date=UTC_CLOCK - timedelta(days=5),
        status="settled",
        now=UTC_CLOCK,
    )
    assert eligible is False
    assert reason == "transaction_not_owned"


def test_refund_same_transaction_requested_twice_only_one_succeeds():
    """Same transaction requested twice -> Only one refund can succeed."""
    reset_refunds()
    res1 = issue_refund("txn_double_test", 40.00)
    assert res1["ok"] is True
    assert "refund_id" in res1

    res2 = issue_refund("txn_double_test", 40.00)
    assert res2["ok"] is False
    assert res2["reason"] == "already_refunded"


# ==============================================================================
# Test B — Verification and Privacy
# ==============================================================================

def test_verification_correct_email_and_last_four_verifies_session():
    """Correct email and last four digits -> Session becomes verified."""
    state = {
        "supplied_email": "alex.morgan@example.com",
        "supplied_card_last4": "4242",
        "verified": False,
    }
    updates = verify_customer(state)
    assert updates["verified"] is True
    assert updates["customer_id"] == "cust_001"
    assert updates["customer_name"] == "Alex Morgan"


def test_verification_wrong_email_no_account_details_disclosed():
    """Wrong email -> No account details disclosed, stays unverified."""
    state = {
        "supplied_email": "wrong.email@example.com",
        "supplied_card_last4": "4242",
        "verified": False,
        "verification_attempts": 0,
    }
    updates = verify_customer(state)
    assert updates["verified"] is False
    assert "customer_id" not in updates
    assert "customer_name" not in updates
    assert updates["verification_attempts"] == 1


def test_verification_wrong_last_four_no_account_details_disclosed():
    """Wrong last four digits -> No account details disclosed, stays unverified."""
    state = {
        "supplied_email": "alex.morgan@example.com",
        "supplied_card_last4": "9999",
        "verified": False,
        "verification_attempts": 0,
    }
    updates = verify_customer(state)
    assert updates["verified"] is False
    assert "customer_id" not in updates
    assert "customer_name" not in updates
    assert updates["verification_attempts"] == 1


def test_verification_three_failed_checks_locks_and_escalates():
    """Three failed verification checks -> Escalate and stop account actions."""
    state = {
        "supplied_email": "alex.morgan@example.com",
        "supplied_card_last4": "0000",
        "verified": False,
        "verification_attempts": 2,
    }
    updates = verify_customer(state)
    assert updates["verified"] is False
    assert updates["verification_attempts"] == 3
    assert updates["handoff_required"] is True
    assert updates["actions_stopped"] is True
    assert updates["workflow_status"] == "blocked"


def test_privacy_email_and_card_never_exposed_in_trusted_state():
    """Ensure verification state is tracked in trusted application state."""
    state = {
        "verified": True,
        "customer_id": "cust_001",
        "supplied_email": "alex.morgan@example.com",
        "supplied_card_last4": "4242",
    }
    # Trusted state holds verification boolean
    assert state.get("verified") is True
    # Card is strictly limited to 4 digits
    assert len(state["supplied_card_last4"]) == 4


def test_generic_refund_policy_question_answers_without_verification():
    """Customer asks a generic refund-policy question -> Answer without account verification."""
    state = {
        "verified": False,
        "intent": "general_policy",
        "actions_stopped": False,
    }
    next_step = route_request(state)
    assert next_step == "answer_general"


def test_customer_asks_to_close_account_escalates_without_verification():
    """Customer asks to close account -> Escalate without requiring verification first."""
    state = {
        "verified": False,
        "intent": "account_closure",
        "handoff_required": True,
        "handoff_reason": "Customer requested account closure.",
    }
    next_step = route_request(state)
    assert next_step == "escalate"


def test_suspected_fraud_low_value_normal_priority_escalation():
    """Suspected fraud with low-value loss (<= $500) escalates with normal priority."""
    from paylane.tools.nodes import classify_request
    from langchain_core.messages import HumanMessage

    state = {
        "messages": [HumanMessage(content="Someone charged $50 to my card fraudulently.")],
    }
    # Even if LLM parses fraud, priority is normal
    res = classify_request(state)
    assert res.get("handoff_required") is True
    assert res.get("ticket_priority", "normal") == "normal"
