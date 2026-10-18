### Agent package exports
# - Exposes the support agent service and graph builder.
# - Provides a function for running one user message.
# - Keeps imports stable for the command line interface.

from __future__ import annotations


def __getattr__(name: str):  # lazy package-level imports to avoid circular deps
    if name == "AgentState":
        from paylane.agent.state import AgentState
        return AgentState
    if name == "build_agent":
        from paylane.agent.graph import build_agent
        return build_agent
    if name == "run_agent":
        from paylane.agent.runner import run_agent
        return run_agent
    if name == "SupportAgent":
        from paylane.agent.service import SupportAgent
        return SupportAgent
    raise AttributeError(f"module 'paylane.agent' has no attribute {name!r}")


__all__ = ["AgentState", "SupportAgent", "build_agent", "run_agent"]
