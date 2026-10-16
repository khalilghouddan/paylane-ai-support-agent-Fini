### Formatted terminal messages for the Paylane AI Support Agent.


from __future__ import annotations

from paylane.style.colors import BOLD, CYAN, GREEN, RED, RESET, YELLOW

def print_user_message(message: str) -> None:
    print(f"\n{CYAN}{BOLD}You:{RESET} {message}")


def print_agent_message(message: str) -> None:
    print(f"\n{GREEN}{BOLD}Paylane AI:{RESET} {message}")


def print_error(message: str) -> None:
    print(f"\n{RED}{BOLD}Error:{RESET} {message}")


def print_info(message: str) -> None:
    print(f"\n{YELLOW}{BOLD}Info:{RESET} {message}")
