"""Human escalation tool."""

from langchain_core.tools import tool

from paylane.data.tickets import (
    escalate_to_human as create_ticket,
)


@tool
def escalate_to_human(
    customer_id: str | None,
    summary: str,
    priority: str = "normal",
) -> dict:
    """Create a human support ticket.

    Use for frozen cards, suspected unauthorized charges, legal threats,
    account closure requests, qualifying fraud, and explicit requests
    to speak with a human. Verification is not required for escalation.
    Do not include full card numbers, passwords, or unnecessary personal data.
    """
    ticket = create_ticket(
        customer_id=customer_id,
        summary=summary,
        priority=priority,
    )

    return {
        "ok": True,
        "ticket_id": ticket["ticket_id"],
        "priority": ticket["priority"],
        "message": "The issue has been referred to human support.",
    }
