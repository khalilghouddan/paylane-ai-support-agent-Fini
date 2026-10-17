###  implementation agent
# Command help display
# - Lists available terminal commands.
# - Explains basic conversation usage.
# - Notes verification and escalation limits.
# TODO: Keep help text aligned with available CLI commands.

from __future__ import annotations

from paylane.style.colors import BOLD, CYAN, RESET


def print_help() -> None:
    """Display available commands and usage instructions."""
    print(f"\n{CYAN}{BOLD}Paylane AI Support — Help{RESET}")
    print("-" * 36)
    print("Type a message to start a support conversation.")
    print()
    print(f"  {BOLD}help{RESET}       Show this help message")
    print(f"  {BOLD}exit{RESET}       End the conversation")
    print(f"  {BOLD}quit{RESET}       End the conversation")
    print()
    print("The agent can help with supported payment questions.")
    print("Account-specific actions require customer verification.")
    print("Some issues must be escalated to a human support agent.")
