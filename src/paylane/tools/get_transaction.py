###  implementation agent
# Transaction lookup tool
# - Retrieves mock transaction details.
# - Limits lookup to the requested customer context.
# - Returns structured transaction data.
# TODO: Complete and maintain the Transaction lookup tool functionality.
"""Transaction lookup tool."""

from langchain_core.tools import tool

from paylane.data.transactions import get_transaction as lookup_transaction


@tool
def get_transaction(customer_id: str, txn_id: str) -> dict:
    """Retrieve a transaction belonging to a specific customer.

    Call only after the customer has been verified.
    Both the customer ID and transaction ID must be supplied.
    """
    transaction = lookup_transaction(customer_id, txn_id)

    if transaction is None:
        return {
            "found": False,
            "message": "Transaction not found for this customer.",
        }

    return {
        "found": True,
        "id": transaction["id"],
        "amount": transaction["amount"],
        "date": transaction["date"],
        "merchant": transaction["merchant"],
        "status": transaction["status"],
    }
