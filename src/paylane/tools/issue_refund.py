"""Policy-enforced refund tool."""

from datetime import UTC, datetime

from langchain_core.tools import tool

from paylane.data.refunds import (
    has_been_refunded,
)
from paylane.data.refunds import (
    issue_refund as record_refund,
)
from paylane.data.transactions import (
    TEST_NOW,
    get_transaction_by_id,
)


@tool
def issue_refund(
    txn_id: str,
    amount: float,
    customer_id: str | None = None,
    verified: bool = True,
) -> dict:
    """Issue an eligible full refund.

    The customer must be verified. Only settled transactions belonging
    to that customer can be refunded. The full original amount must be
    at most $75 and the transaction must be less than 30 days old.
    Transactions requiring escalation must not be refunded.
    """
    if verified is not True:
        return {"ok": False, "reason": "customer_not_verified"}

    transaction = get_transaction_by_id(txn_id)

    if transaction is None:
        return {"ok": False, "reason": "transaction_not_found"}

    # Prevent cross-customer refunds when customer context is provided.
    if customer_id and transaction["customer_id"] != customer_id:
        return {"ok": False, "reason": "transaction_ownership_mismatch"}

    if transaction["status"] == "pending":
        return {"ok": False, "reason": "pending_transaction"}

    if transaction["status"] == "refunded":
        return {"ok": False, "reason": "already_refunded"}

    if transaction["status"] != "settled":
        return {"ok": False, "reason": "transaction_not_settled"}

    original_amount = float(transaction["amount"])

    # No partial refunds or split requests.
    if float(amount) != original_amount:
        return {"ok": False, "reason": "full_refund_only"}

    if original_amount > 75:
        return {"ok": False, "reason": "amount_requires_escalation"}

    transaction_date = datetime.fromisoformat(transaction["date"]).astimezone(UTC)
    now = TEST_NOW.astimezone(UTC)
    age = now - transaction_date

    # Exactly 30 days is not eligible.
    if age.total_seconds() < 0:
        return {"ok": False, "reason": "invalid_future_transaction_date"}

    if age.total_seconds() >= 30 * 24 * 60 * 60:
        return {"ok": False, "reason": "transaction_requires_escalation"}

    if has_been_refunded(txn_id):
        return {"ok": False, "reason": "already_refunded"}

    # Record the refund safely in the mock ledger.
    return record_refund(txn_id, original_amount)
