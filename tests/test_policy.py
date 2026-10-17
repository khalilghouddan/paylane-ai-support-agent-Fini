"""Unit tests for deterministic refund policy checks."""

from datetime import timedelta

from paylane.agent.guards import check_refund_eligibility
from paylane.data.transactions import TEST_NOW
from paylane.policy import RefundDecision, evaluate_refund


def test_evaluate_refund_eligible():
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.APPROVE
    assert reason == "eligible"


def test_evaluate_refund_unverified():
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="settled",
        verified=False,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.DENY
    assert reason == "customer_not_verified"


def test_evaluate_refund_over_75_escalates():
    decision, reason = evaluate_refund(
        amount=75.01,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.ESCALATE
    assert reason == "amount_requires_escalation"


def test_evaluate_refund_exactly_75_approved():
    decision, reason = evaluate_refund(
        amount=75.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.APPROVE
    assert reason == "eligible"


def test_evaluate_refund_30_days_or_older_escalates():
    # Exactly 30 days old
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=30),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.ESCALATE
    assert reason == "transaction_requires_escalation"


def test_evaluate_refund_29_days_approved():
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=29, hours=23),
        transaction_status="settled",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.APPROVE
    assert reason == "eligible"


def test_evaluate_refund_pending_rejected():
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="pending",
        verified=True,
        already_refunded=False,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.DENY
    assert reason == "pending_transaction"


def test_evaluate_refund_already_refunded_rejected():
    decision, reason = evaluate_refund(
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        transaction_status="refunded",
        verified=True,
        already_refunded=True,
        now=TEST_NOW,
    )
    assert decision == RefundDecision.DENY
    assert reason == "already_refunded"


def test_check_refund_eligibility_ownership():
    eligible, reason = check_refund_eligibility(
        verified=True,
        owns_transaction=False,
        amount=45.00,
        transaction_date=TEST_NOW - timedelta(days=5),
        status="settled",
        now=TEST_NOW,
    )
    assert eligible is False
    assert reason == "transaction_not_owned"
