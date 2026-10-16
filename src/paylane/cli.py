###Command-line interface for the Paylane AI support agent.


#Provides an interactive terminal interface for the Paylane AI Support Agent.
#It accepts customer messages, sends them to SupportAgent, displays responses,and handles session termination and errors.

#TODO: Implement the main function to run the command-line interface.
#TODO: 



# Allows type annotations to be evaluated later.
from __future__ import annotations
# loggs module logging.warning(",logging.error("A
import logging
#create comand for cli
import typer

# text format and color in terminal output
from rich.console import Console
#dispaly content inside box
from rich.panel import Panel
#display text
from rich.prompt import Prompt
#text object with style
from rich.text import Text

# Import my ai agent 
from paylane.agent import SupportAgent


# create cli application using typer framework
app = typer.Typer(
    name="paylane",
    help="Interact with the Paylane AI support agent.",
    add_completion=False,
)
#creatz console
console = Console()
#create looger 
logger = logging.getLogger(__name__)


#tell typer this is the main with @app.callback()
# create the main fuction 
@app.callback()
def main() -> None:
    """Paylane AI support agent CLI."""


#create the chat command
@app.command()
def chat(
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Display diagnostic information.",
    ),
) -> None:
    """Start an interactive support conversation."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        # The SupportAgent class must be implemented in agent.py.
        agent = SupportAgent()
    except Exception:
        logger.exception("Failed to initialize the support agent.")
        console.print(
            "[bold red]Error:[/bold red] Could not initialize the agent. "
            "Check your configuration and model settings."
        )
        raise typer.Exit(code=1) from None

    console.print()
    console.print(
        Panel(
            "[bold cyan]Paylane AI Support Agent[/bold cyan]\n"
            "Ask about refunds, transactions, or card issues.\n"
            "[dim]Type 'exit' or 'quit' to end the session.[/dim]",
            title="Customer Support",
            border_style="cyan",
        )
    )

    while True:
        try:
            message = Prompt.ask("\n[bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Session ended.[/yellow]")
            break

        if not message:
            console.print("[dim]Please enter a message.[/dim]")
            continue

        if message.casefold() in {"exit", "quit"}:
            console.print("[yellow]Session ended. Goodbye![/yellow]")
            break

        try:
            # Expected interface:
            # agent.respond(message: str) -> str
            response = agent.respond(message)

            console.print(
                Panel(
                    Text(str(response)),
                    title="[bold blue]Paylane Agent[/bold blue]",
                    border_style="blue",
                )
            )
        except Exception:
            logger.exception("Failed to process customer message.")
            console.print(
                "[bold red]Sorry, something went wrong.[/bold red] "
                "Please try again."
            )


if __name__ == "__main__":
    app()
