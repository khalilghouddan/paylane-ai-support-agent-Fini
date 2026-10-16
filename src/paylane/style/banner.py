### Dispays the application banner with ANSI colors and formatting.


from __future__ import annotations

import os

from paylane.style.colors import BOLD, CYAN, RESET


def print_banner() -> None:
    
    # Enable ANSI colors in supported Windows terminals.
    if os.name == "nt":
        os.system("")

    banner = r"""
 ____   _   _ __   __ _      _   _  _____
|  _ \ / \ | |\ \ / /| |    / \ | |/ ____|
| |_) / _ \| | \ V / | |   / _ \| | |
|  __/ ___ \ |  | |  | |__/ ___ \ | |____
|_| /_/   \_\_|  |_|  |____/_/   \_\_|\_____|
"""

    print(f"{CYAN}{BOLD}{banner}{RESET}")
    print(f"{BOLD}        AI CUSTOMER SUPPORT AGENT{RESET}")
    print("        Type 'help' for commands.")
    print("        Type 'exit' or 'quit' to end the session.")
