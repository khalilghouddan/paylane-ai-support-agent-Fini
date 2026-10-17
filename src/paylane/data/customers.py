###  Mock customer records
# - Contains the Mock customer records package code.
# - Provides functionality to related Paylane modules.
# - Defines this module package boundary.
# TODO:


# deepcopy send data copy
from copy import deepcopy

# dictionary of mock customer records
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


# get_customer_by_id
def get_customer(email: str) -> dict | None:
    # remove spacees to compere
    normalized_email = email.strip().casefold()

    for customer in CUSTOMERS.values():
        if customer["email"].casefold() == normalized_email:
            return deepcopy(customer)

    return None


# get_customer_by_id
def get_customer_by_id(customer_id: str) -> dict | None:
    customer = CUSTOMERS.get(customer_id)
    return deepcopy(customer) if customer else None
