"""Paylane Support Agent LangGraph workflow.

Wires together the graph nodes (defined in paylane.tools.nodes) with
routing functions and compiles the StateGraph.  All business logic lives
in nodes.py; this file is intentionally kept small.
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph

from paylane.agent.state import AgentState, SupportState
from paylane.tools.nodes import (
    answer_general_node,
    check_safety_and_policy,
    classify_request,
    compose_response_node,
    decide_refund,
    escalate_node,
    issue_refund_node,
    lookup_transaction_node,
    verify_customer,
)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_request(
    state: AgentState,
) -> Literal["escalate", "answer_general", "verify", "lookup_transaction", "compose_response"]:
    """Route the request based on safety, verification, and intent."""
    if state.get("actions_stopped"):
        return "compose_response"

    if state.get("handoff_required"):
        return "escalate"

    if state.get("intent") == "general_policy":
        return "answer_general"

    if not state.get("verified"):
        return "verify"

    if state.get("intent") == "frozen_card":
        if state.get("customer_status") == "frozen":
            return "escalate"
        return "compose_response"

    if state.get("intent") in ("refund", "transaction_query"):
        if state.get("transaction_id"):
            return "lookup_transaction"
        return "compose_response"

    return "compose_response"


def route_after_verify(
    state: AgentState,
) -> Literal["escalate", "lookup_transaction", "compose_response"]:
    """Route after customer verification step."""
    if state.get("handoff_required"):
        return "escalate"

    if (
        state.get("verified")
        and state.get("intent") in ("refund", "transaction_query")
        and state.get("transaction_id")
    ):
        return "lookup_transaction"

    return "compose_response"


def route_refund(
    state: AgentState,
) -> Literal["issue_refund", "escalate", "compose_response"]:
    """Route based on deterministic refund decision."""
    if state.get("handoff_required"):
        return "escalate"

    if state.get("refund_eligible"):
        return "issue_refund"

    return "compose_response"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_agent() -> StateGraph:
    """Build and compile the Paylane support agent LangGraph workflow."""
    builder = StateGraph(AgentState)

    builder.add_node("classify_request", classify_request)
    builder.add_node("check_safety_and_policy", check_safety_and_policy)
    builder.add_node("verify", verify_customer)
    builder.add_node("lookup_transaction", lookup_transaction_node)
    builder.add_node("decide_refund", decide_refund)
    builder.add_node("issue_refund", issue_refund_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("answer_general", answer_general_node)
    builder.add_node("compose_response", compose_response_node)

    builder.add_edge(START, "classify_request")
    builder.add_edge("classify_request", "check_safety_and_policy")

    builder.add_conditional_edges("check_safety_and_policy", route_request)
    builder.add_conditional_edges("verify", route_after_verify)

    builder.add_edge("lookup_transaction", "decide_refund")
    builder.add_conditional_edges("decide_refund", route_refund)

    builder.add_edge("issue_refund", "compose_response")
    builder.add_edge("escalate", "compose_response")
    builder.add_edge("answer_general", "compose_response")
    builder.add_edge("compose_response", END)

    return builder.compile()


support_graph = build_agent()

__all__ = [
    "AgentState",
    "SupportState",
    "build_agent",
    "route_after_verify",
    "route_refund",
    "route_request",
    "support_graph",
]
