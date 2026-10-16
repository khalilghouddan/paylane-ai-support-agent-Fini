###   Mock customer records and customer lookup


from copy import deepcopy

CUSTOMERS: dict[str, dict] = {
    "cust_001": {
        "id": "cust_001",
        "name": "Alex Morgan",
        "email": "alex.morgan@example.com",
        "card_last4": "4242",
        "status": "active",
        "verified": False,
    },
    "cust_002": {
        "id": "cust_002",
        "name": "Jamie Lee",
        "email": "jamie.lee@example.com",
        "card_last4": "1111",
        "status": "frozen",
        "verified": False,
    },
    "cust_003": {
        "id": "cust_003",
        "name": "Taylor Smith",
        "email": "taylor.smith@example.com",
        "card_last4": "5678",
        "status": "active",
        "verified": False,
    },
}


def get_customer(email: str) -> dict | None:
    normalized_email = email.strip().casefold()

    for customer in CUSTOMERS.values():
        if customer["email"].casefold() == normalized_email:
            return deepcopy(customer)

    return None


def get_customer_by_id(customer_id: str) -> dict | None:
    """Return a copy of a customer record by ID."""
    customer = CUSTOMERS.get(customer_id)
    return deepcopy(customer) if customer else None