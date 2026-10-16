"""Mock refund records and duplicate-refund protection."""

from threading import Lock
from uuid import uuid4

REFUNDS: dict[str, dict] = {}
_REFUNDED_TRANSACTION_IDS: set[str] = set()
_REFUND_LOCK = Lock()


def has_been_refunded(txn_id: str) -> bool:
    """Check whether a transaction already has a successful refund."""
    with _REFUND_LOCK:
        return txn_id in _REFUNDED_TRANSACTION_IDS


def issue_refund(txn_id: str, amount: float) -> dict:
    """
    Record a mock refund.

    This function is an API simulation, not the policy engine.
    Eligibility must be checked before calling it.
    """
    if amount <= 0:
        return {"ok": False, "reason": "invalid_amount"}

    with _REFUND_LOCK:
        if txn_id in _REFUNDED_TRANSACTION_IDS:
            return {"ok": False, "reason": "already_refunded"}

        refund_id = f"ref_{uuid4().hex[:12]}"

        refund = {
            "refund_id": refund_id,
            "txn_id": txn_id,
            "amount": round(amount, 2),
            "status": "succeeded",
        }

        REFUNDS[refund_id] = refund
        _REFUNDED_TRANSACTION_IDS.add(txn_id)

        return {"ok": True, "refund_id": refund_id}


def get_refund_by_transaction(txn_id: str) -> dict | None:
    """Return the successful refund associated with a transaction."""
    with _REFUND_LOCK:
        for refund in REFUNDS.values():
            if refund["txn_id"] == txn_id:
                return refund.copy()

    return None


def reset_refunds() -> None:
    """Reset mock refund state between isolated tests."""
    with _REFUND_LOCK:
        REFUNDS.clear()
        _REFUNDED_TRANSACTION_IDS.clear()