"""Decepticon CLI - Agent Harness for Pentesting with AI."""

import typer
from rich.console import Console
from rich.panel import Panel
from decepticon_cli import __version__

app = typer.Typer(
    name="decepticon",
    help="Agente autónomo CLI para pentesting con IA",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version():
    """Mostrar versión."""
    console.print(f"[bold cyan]Decepticon CLI[/] v{__version__}")


@app.command()
def config(
    key: str = typer.Argument(..., help="Clave de configuración"),
    value: str = typer.Option(None, help="Valor a establecer"),
):
    """Gestionar configuración."""
    from decepticon_cli.config import ConfigManager
    cm = ConfigManager()
    if value:
        cm.set(key, value)
        console.print(f"[green]✓[/] {key} configurado")
    else:
        val = cm.get(key)
        console.print(f"[cyan]{key}[/] = {val}")


@app.command()
def start(
    model: str = typer.Option("gpt-4o", help="Modelo LLM a usar"),
    target: str = typer.Option(None, help="Target IP/Range"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Modo verbose"),
):
    """Iniciar agente autónomo."""
    from decepticon_cli.agent import Agent
    from decepticon_cli.llm import LLMProvider

    console.print(Panel("[bold red]DECEPTICON[/] - Agent Harness", style="red"))
    
    llm = LLMProvider(model=model)
    agent = Agent(llm=llm, verbose=verbose)
    
    if target:
        agent.target = target
        console.print(f"[yellow]Target:[/] {target}")
    
    agent.run()


@app.command()
def engage(
    target: str = typer.Argument(..., help="Target IP/Range"),
    profile: str = typer.Option("default", help="Engagement profile"),
    rules: str = typer.Option(None, "--rules-file", help="Rules of Engagement file"),
):
    """Iniciar engagement contra target."""
    from decepticon_cli.agent import Agent
    from decepticon_cli.llm import LLMProvider
    from decepticon_cli.config import ConfigManager

    console.print(Panel(f"[bold red]ENGAGEMENT[/] → {target}", style="red"))
    
    cm = ConfigManager()
    model = cm.get("model", "gpt-4o")
    
    llm = LLMProvider(model=model)
    agent = Agent(llm=llm, target=target, profile=profile)
    
    if rules:
        agent.load_rules(rules)
    
    agent.run()


@app.command()
def skills():
    """Listar skills disponibles."""
    from decepticon_cli.tools import ToolRegistry
    registry = ToolRegistry()
    registry.list_skills()


if __name__ == "__main__":
    app()