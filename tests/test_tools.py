"""Unit tests for Paylane tools and atomic operations."""

from concurrent.futures import ThreadPoolExecutor

from paylane.data import get_ticket, reset_refunds, reset_tickets
from paylane.data.refunds import get_refund_by_transaction
from paylane.tools import (
    escalate_to_human,
    get_customer,
    get_transaction,
    issue_refund,
)


def test_get_customer_found():
    """get_customer finds the correct mock customer."""
    result = get_customer.invoke({"email": "alex.morgan@example.com"})
    assert result["found"] is True
    assert result["id"] == "cust_001"
    assert result["card_last4"] == "4242"
    assert result["status"] == "active"
    # Never expose stored email in customer output
    assert "email" not in result


def test_get_customer_not_found():
    """get_customer returns not found for unknown email."""
    result = get_customer.invoke({"email": "nonexistent@example.com"})
    assert result["found"] is False


def test_get_transaction_verified_owner():
    """get_transaction retrieves the transaction for the correct customer."""
    result = get_transaction.invoke({"customer_id": "cust_001", "txn_id": "txn_001"})
    assert result["found"] is True
    assert result["id"] == "txn_001"
    assert result["amount"] == 45.00
    assert result["status"] == "settled"


def test_get_transaction_ownership_mismatch():
    """get_transaction returns not found when customer doesn't own transaction."""
    # txn_006 belongs to cust_002, not cust_001
    result = get_transaction.invoke({"customer_id": "cust_001", "txn_id": "txn_006"})
    assert result["found"] is False


def test_issue_refund_success():
    """issue_refund processes valid refund and records transaction state."""
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

    # Verify transaction state reflects the recorded refund
    recorded = get_refund_by_transaction("txn_001")
    assert recorded is not None
    assert recorded["refund_id"] == result["refund_id"]
    assert recorded["status"] == "succeeded"


def test_issue_refund_duplicate_rejected():
    """issue_refund refuses duplicate refund on same transaction."""
    reset_refunds()
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


def test_issue_refund_atomic_concurrency():
    """Atomic duplicate-refund prevention prevents race conditions under concurrency."""
    reset_refunds()
    txn_id = "txn_001"

    def attempt_refund():
        return issue_refund.invoke(
            {
                "txn_id": txn_id,
                "amount": 45.00,
                "customer_id": "cust_001",
                "verified": True,
            }
        )

    # Launch 10 simultaneous threads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_refund) for _ in range(10)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r.get("ok") is True]
    duplicates = [r for r in results if r.get("reason") == "already_refunded"]

    # Exactly one thread must succeed, nine must be safely rejected
    assert len(successes) == 1
    assert len(duplicates) == 9


def test_issue_refund_unverified_rejected():
    """issue_refund rejects unverified customer."""
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
    """issue_refund rejects amount requiring escalation (> $75)."""
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
    """issue_refund rejects partial refund requests."""
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
    """escalate_to_human creates a ticket with normal priority."""
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
    """escalate_to_human creates a ticket with high priority."""
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


def test_escalate_to_human_null_customer_id_guest():
    """escalate_to_human accepts null customer ID for guest escalation."""
    reset_tickets()
    result = escalate_to_human.invoke(
        {
            "customer_id": None,
            "summary": "Guest user requests escalation without verification.",
            "priority": "normal",
        }
    )
    assert result["ok"] is True
    assert "ticket_id" in result
    ticket = get_ticket(result["ticket_id"])
    assert ticket is not None
    assert ticket["customer_id"] is None
