"""Agent invocation helpers."""

from langchain_core.messages import AIMessage, HumanMessage


def run_agent(agent, user_message: str) -> str:
    """Run a single user turn through the compiled graph."""
    result = agent.invoke({"messages": [HumanMessage(content=user_message)]})

    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)

    return "I'm sorry, I couldn't generate a response. Please try again."


__all__ = ["run_agent"]
