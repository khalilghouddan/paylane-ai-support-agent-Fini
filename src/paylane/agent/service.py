"""Support agent service.

Maintains multi-turn conversation state and executes turns through
the compiled LangGraph workflow.
"""

from langchain_core.messages import AIMessage, HumanMessage

from paylane.agent.graph import build_agent


class SupportAgent:
    """Stateful support agent session."""

    def __init__(self) -> None:
        self._graph = build_agent()
        self._state: dict = {
            "messages": [],
            "verification_attempts": 0,
            "actions_stopped": False,
        }

    @property
    def state(self) -> dict:
        """Access current session state."""
        return self._state

    def chat(self, message: str) -> str:
        """Send a message to the agent and receive a response."""
        user_msg = HumanMessage(content=message)
        self._state["messages"] = list(self._state.get("messages", [])) + [user_msg]

        self._state = self._graph.invoke(self._state)

        for msg in reversed(self._state.get("messages", [])):
            if isinstance(msg, AIMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content)

        return "I'm sorry, I couldn't generate a response. Please try again."

    def reset(self) -> None:
        """Reset conversation state for a new session."""
        self._state = {
            "messages": [],
            "verification_attempts": 0,
            "actions_stopped": False,
        }


__all__ = ["SupportAgent"]
