# Refund policy checks
# - Checks verification and transaction status.
# - Applies refund amount and age limits.
# - Returns approve, deny, or escalate decisions.

from datetime import UTC, datetime
from enum import Enum


class RefundDecision(str, Enum):
    APPROVE = "approve"
    ESCALATE = "escalate"
    DENY = "deny"


def evaluate_refund(
    *,
    amount: float,
    transaction_date: datetime,
    transaction_status: str,
    verified: bool,
    already_refunded: bool,
    now: datetime,
    refund_limit: float = 75.00,
    refund_window_days: int = 30,
) -> tuple[RefundDecision, str]:
    """Evaluate a full refund against Paylane's refund policy."""

    if not verified:
        return RefundDecision.DENY, "customer_not_verified"

    if already_refunded or transaction_status == "refunded":
        return RefundDecision.DENY, "already_refunded"

    if transaction_status == "pending":
        return RefundDecision.DENY, "pending_transaction"

    if transaction_status != "settled":
        return RefundDecision.DENY, "transaction_not_settled"

    if amount <= 0:
        return RefundDecision.DENY, "invalid_amount"

    if amount > refund_limit:
        return RefundDecision.ESCALATE, "amount_requires_escalation"

    if transaction_date.tzinfo is None or now.tzinfo is None:
        return RefundDecision.DENY, "timezone_required"

    transaction_date = transaction_date.astimezone(UTC)
    now = now.astimezone(UTC)

    age = now - transaction_date

    if age.total_seconds() < 0:
        return RefundDecision.DENY, "future_transaction_date"

    if age.total_seconds() >= refund_window_days * 24 * 60 * 60:
        return RefundDecision.ESCALATE, "transaction_requires_escalation"

    return RefundDecision.APPROVE, "eligible"
