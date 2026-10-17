"""Unit tests for LangGraph state machine and nodes."""

from langchain_core.messages import HumanMessage

from paylane.agent.graph import (
    classify_request,
    route_refund,
    route_request,
    verify_customer,
)


def test_classify_request_intents():
    # Legal intent
    res = classify_request(
        {"messages": [HumanMessage(content="I will sue your company!")]}
    )
    assert res["intent"] == "legal_action"
    assert res["handoff_required"] is True

    # Account closure intent
    res = classify_request(
        {"messages": [HumanMessage(content="Please close my account.")]}
    )
    assert res["intent"] == "account_closure"
    assert res["handoff_required"] is True

    # Human request intent
    res = classify_request(
        {"messages": [HumanMessage(content="I want to speak with a human agent")]}
    )
    assert res["intent"] == "human_request"
    assert res["handoff_required"] is True

    # Fraud with high loss (> $500)
    res = classify_request(
        {
            "messages": [
                HumanMessage(content="Someone made an unauthorized purchase of $800!")
            ]
        }
    )
    assert res["intent"] == "suspected_fraud"
    assert res["handoff_required"] is True
    assert res["ticket_priority"] == "high"

    # General policy question
    res = classify_request(
        {"messages": [HumanMessage(content="What is your refund policy?")]}
    )
    assert res["intent"] == "general_policy"


def test_verify_customer_three_attempts_lockout():
    state = {
        "supplied_email": "wrong@example.com",
        "supplied_card_last4": "0000",
        "verification_attempts": 0,
        "verified": False,
    }

    # Attempt 1
    res1 = verify_customer(state)
    assert res1["verification_attempts"] == 1
    assert res1["verified"] is False
    assert res1.get("actions_stopped") is not True

    # Attempt 2
    state["verification_attempts"] = 1
    res2 = verify_customer(state)
    assert res2["verification_attempts"] == 2
    assert res2["verified"] is False
    assert res2.get("actions_stopped") is not True

    # Attempt 3 -> Lockout & Escalation
    state["verification_attempts"] = 2
    res3 = verify_customer(state)
    assert res3["verification_attempts"] == 3
    assert res3["verified"] is False
    assert res3["handoff_required"] is True
    assert res3["actions_stopped"] is True
    assert res3["workflow_status"] == "blocked"


def test_routing_after_lockout():
    state = {
        "actions_stopped": True,
        "handoff_required": True,
        "ticket_id": "ticket_123",
    }
    assert route_request(state) == "compose_response"


def test_routing_unverified():
    state = {"verified": False, "intent": "refund"}
    assert route_request(state) == "verify"


def test_routing_general_policy():
    state = {"verified": False, "intent": "general_policy"}
    assert route_request(state) == "answer_general"


def test_route_refund_outcomes():
    # Approve
    assert route_refund({"refund_eligible": True}) == "issue_refund"
    # Escalate
    assert route_refund({"handoff_required": True}) == "escalate"
    # Deny
    assert route_refund({"refund_eligible": False}) == "compose_response"
