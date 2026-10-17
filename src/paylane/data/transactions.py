###  Mock transaction records
# - Contains the Mock transaction records package code.
# - Provides functionality to related Paylane modules.
# -
# TODO:


from copy import deepcopy
from datetime import UTC, datetime

TEST_NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

TRANSACTIONS: dict[str, dict] = {
    "txn_001": {
        "id": "txn_001",
        "customer_id": "cust_001",
        "amount": 45.00,
        "date": "2026-10-10T10:00:00Z",
        "merchant": "Coffee House",
        "status": "settled",
    },
    "txn_002": {
        "id": "txn_002",
        "customer_id": "cust_001",
        "amount": 120.00,
        "date": "2026-10-12T14:00:00Z",
        "merchant": "Electronics Store",
        "status": "settled",
    },
    "txn_003": {
        "id": "txn_003",
        "customer_id": "cust_001",
        "amount": 25.00,
        "date": "2026-10-15T09:00:00Z",
        "merchant": "Book Shop",
        "status": "pending",
    },
    "txn_004": {
        "id": "txn_004",
        "customer_id": "cust_001",
        "amount": 35.00,
        "date": "2026-09-16T12:00:00Z",
        "merchant": "Clothing Store",
        "status": "settled",
    },
    "txn_005": {
        "id": "txn_005",
        "customer_id": "cust_001",
        "amount": 20.00,
        "date": "2026-10-08T11:00:00Z",
        "merchant": "Grocery Store",
        "status": "refunded",
    },
    "txn_006": {
        "id": "txn_006",
        "customer_id": "cust_002",
        "amount": 60.00,
        "date": "2026-10-11T13:00:00Z",
        "merchant": "Online Store",
        "status": "settled",
    },
    "txn_007": {
        "id": "txn_007",
        "customer_id": "cust_003",
        "amount": 70.00,
        "date": "2026-10-14T15:00:00Z",
        "merchant": "Restaurant",
        "status": "settled",
    },
}


def get_transaction(customer_id: str, txn_id: str) -> dict | None:
    transaction = TRANSACTIONS.get(txn_id)
    if transaction is None:
        return None
    if transaction["customer_id"] != customer_id:
        return None
    return deepcopy(transaction)


def get_transaction_by_id(txn_id: str) -> dict | None:
    transaction = TRANSACTIONS.get(txn_id)
    return deepcopy(transaction) if transaction else None
