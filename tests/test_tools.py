"""Unit tests for Paylane tools."""

from paylane.data import reset_refunds, reset_tickets
from paylane.tools import (
    escalate_to_human,
    get_customer,
    get_transaction,
    issue_refund,
)


def test_get_customer_found():
    result = get_customer.invoke({"email": "alex.morgan@example.com"})
    assert result["found"] is True
    assert result["id"] == "cust_001"
    assert result["card_last4"] == "4242"
    assert result["status"] == "active"
    # Never expose stored email in customer output
    assert "email" not in result


def test_get_customer_not_found():
    result = get_customer.invoke({"email": "nonexistent@example.com"})
    assert result["found"] is False


def test_get_transaction_verified_owner():
    result = get_transaction.invoke({"customer_id": "cust_001", "txn_id": "txn_001"})
    assert result["found"] is True
    assert result["id"] == "txn_001"
    assert result["amount"] == 45.00
    assert result["status"] == "settled"


def test_get_transaction_ownership_mismatch():
    # txn_006 belongs to cust_002, not cust_001
    result = get_transaction.invoke({"customer_id": "cust_001", "txn_id": "txn_006"})
    assert result["found"] is False


def test_issue_refund_success():
    reset_refunds()
    result = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 45.00,
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert result["ok"] is True
    assert "refund_id" in result


def test_issue_refund_duplicate_rejected():
    reset_refunds()
    # First refund
    res1 = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 45.00,
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert res1["ok"] is True

    # Duplicate attempt
    res2 = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 45.00,
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert res2["ok"] is False
    assert res2["reason"] == "already_refunded"


def test_issue_refund_unverified_rejected():
    reset_refunds()
    result = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 45.00,
            "customer_id": "cust_001",
            "verified": False,
        }
    )
    assert result["ok"] is False
    assert result["reason"] == "customer_not_verified"


def test_issue_refund_over_limit_rejected():
    reset_refunds()
    result = issue_refund.invoke(
        {
            "txn_id": "txn_002",
            "amount": 120.00,
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert result["ok"] is False
    assert result["reason"] == "amount_requires_escalation"


def test_issue_refund_partial_rejected():
    reset_refunds()
    result = issue_refund.invoke(
        {
            "txn_id": "txn_001",
            "amount": 20.00,  # original is $45.00
            "customer_id": "cust_001",
            "verified": True,
        }
    )
    assert result["ok"] is False
    assert result["reason"] == "full_refund_only"


def test_escalate_to_human_normal_priority():
    reset_tickets()
    result = escalate_to_human.invoke(
        {
            "customer_id": "cust_001",
            "summary": "Customer requested assistance with a frozen card.",
            "priority": "normal",
        }
    )
    assert result["ok"] is True
    assert result["priority"] == "normal"
    assert "ticket_id" in result


def test_escalate_to_human_high_priority():
    reset_tickets()
    result = escalate_to_human.invoke(
        {
            "customer_id": "cust_001",
            "summary": "Unauthorized charge of $650 reported.",
            "priority": "high",
        }
    )
    assert result["ok"] is True
    assert result["priority"] == "high"
    assert "ticket_id" in result
