from datetime import UTC, datetime


def check_refund_eligibility(
    *,
    verified: bool,
    owns_transaction: bool,
    amount: float,
    transaction_date: datetime,
    status: str,
    now: datetime,
) -> tuple[bool, str]:

    if not verified:
        return False, "customer_not_verified"

    if not owns_transaction:
        return False, "transaction_not_owned"

    if status == "refunded":
        return False, "already_refunded"

    if status == "pending":
        return False, "transaction_pending"

    if status != "settled":
        return False, "unsupported_transaction_status"

    if amount <= 0:
        return False, "invalid_amount"

    if amount > 75:
        return False, "amount_exceeds_limit"

    transaction_date = transaction_date.replace(tzinfo=transaction_date.tzinfo or UTC)
    now = now.replace(tzinfo=now.tzinfo or UTC)

    age = now - transaction_date

    if age.total_seconds() < 0:
        return False, "transaction_date_in_future"

    if age.total_seconds() >= 30 * 24 * 60 * 60:
        return False, "transaction_30_days_or_older"

    return True, "eligible"
