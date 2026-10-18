###  Mock human-escalation ticket records.


from threading import Lock
from uuid import uuid4

TICKETS: dict[str, dict] = {}
_TICKET_LOCK = Lock()


def escalate_to_human(
    customer_id: str | None,
    summary: str | None = None,
    priority: str = "normal",
) -> dict:
    clean_summary = (summary or "").strip()
    if not clean_summary:
        clean_summary = "Customer inquiry requires human assistance."

    with _TICKET_LOCK:
        ticket_id = f"ticket_{uuid4().hex[:12]}"

        TICKETS[ticket_id] = {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "summary": clean_summary,
            "status": "open",
            "priority": priority or "normal",
        }

        return {"ticket_id": ticket_id, "priority": priority}


def get_ticket(ticket_id: str) -> dict | None:
    ticket = TICKETS.get(ticket_id)
    return ticket.copy() if ticket else None


def reset_tickets() -> None:
    with _TICKET_LOCK:
        TICKETS.clear()
