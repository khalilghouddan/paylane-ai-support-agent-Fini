### Command line interface
# - Runs the interactive customer support session.
# - Displays messages and command help.
# - Handles exit and runtime errors.
# TODO: Complete interactive CLI behavior and error handling.


# Allows type annotations to be evaluated later.
from __future__ import annotations

# loggs module logging.warning(",logging.error("A
import logging

from paylane import style
from paylane.agent import SupportAgent

logger = logging.getLogger(__name__)


# Start an interactive customer-support conversation."""
def run_chat() -> None:

    try:
        agent = SupportAgent()
    except Exception:
        logger.exception("Failed to initialize the support agent.")
        style.print_error(
            "Could not start the agent. Check your configuration and API key."
        )
        return

    style.print_banner()

    while True:
        try:
            user_message = input("\nYou: ").strip()

            if not user_message:
                continue

            if user_message.lower() in {"exit", "quit"}:
                style.print_info("Conversation ended. Goodbye!")
                break

            if user_message.lower() == "help":
                style.print_help()
                continue

            style.print_user_message(user_message)

            response = agent.chat(user_message)

            style.print_agent_message(response)

        except KeyboardInterrupt:
            style.print_info("\nConversation interrupted. Goodbye!")
            break

        except EOFError:
            style.print_info("\nInput closed. Goodbye!")
            break

        except Exception:
            logger.exception("An error occurred while processing the message.")
            style.print_error("Sorry, something went wrong. Please try again.")


# Application entry point.
def main() -> None:

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    run_chat()


if __name__ == "__main__":
    main()
