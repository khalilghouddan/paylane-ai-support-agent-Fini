"""Mock human-escalation ticket records."""

from threading import Lock
from uuid import uuid4

TICKETS: dict[str, dict] = {}
_TICKET_LOCK = Lock()


def escalate_to_human(
    customer_id: str | None,
    summary: str,
) -> dict:
    """Create a mock support ticket without exposing sensitive details."""
    if not summary.strip():
        raise ValueError("Ticket summary cannot be empty.")

    with _TICKET_LOCK:
        ticket_id = f"ticket_{uuid4().hex[:12]}"

        TICKETS[ticket_id] = {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "summary": summary.strip(),
            "status": "open",
            "priority": "normal",
        }

        return {"ticket_id": ticket_id}


def get_ticket(ticket_id: str) -> dict | None:
    """Return a copy of a ticket if it exists."""
    ticket = TICKETS.get(ticket_id)
    return ticket.copy() if ticket else None


def reset_tickets() -> None:
    """Clear mock tickets between isolated tests."""
    with _TICKET_LOCK:
        TICKETS.clear()