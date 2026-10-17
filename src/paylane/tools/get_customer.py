###  implementation agent
# Customer lookup tool
# - Retrieves mock customer records.
# - Supports verification workflows.
# - Avoids exposing unnecessary account details.
# TODO: Complete and maintain the Customer lookup tool functionality.
"""Customer lookup tool."""

from langchain_core.tools import tool

from paylane.data.customers import get_customer as lookup_customer


@tool
def get_customer(email: str) -> dict:
    """Look up a customer by the email they supplied.

    Use this to retrieve a mock customer record for verification.
    Never reveal the stored email or full card details to the customer.
    """
    customer = lookup_customer(email)

    if customer is None:
        return {"found": False, "message": "Customer not found."}

    # Return only the fields needed by the verification workflow.
    return {
        "found": True,
        "id": customer["id"],
        "name": customer["name"],
        "card_last4": customer["card_last4"],
        "status": customer["status"],
    }
