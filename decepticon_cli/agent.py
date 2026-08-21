"""Core Agent - Loop principal del agente autónomo."""

from __future__ import annotations
import json
import time
from typing import Any
from rich.console import Console
from rich.panel import Panel
from decepticon_cli.llm import LLMProvider
from decepticon_cli.memory import Memory
from decepticon_cli.tools import ToolRegistry

console = Console()


class Agent:
    """Agente autónomo de pentesting."""

    def __init__(
        self,
        llm: LLMProvider,
        target: str | None = None,
        profile: str = "default",
        verbose: bool = False,
        max_iterations: int = 50,
    ):
        self.llm = llm
        self.target = target
        self.profile = profile
        self.verbose = verbose
        self.max_iterations = max_iterations
        self.memory = Memory()
        self.tools = ToolRegistry()
        self.system_prompt = self._build_system_prompt()
        self.running = False

    def _build_system_prompt(self) -> str:
        return f"""You are Decepticon, an autonomous red team AI agent.
Target: {self.target or 'Not specified'}
Profile: {self.profile}

You have access to these tool categories:
- Reconnaissance (port scanning, service enumeration)
- Exploitation (vulnerability testing)
- Post-exploitation (privilege escalation, lateral movement)

RULES:
1. Always verify before exploiting
2. Document every finding
3. Stay within Rules of Engagement
4. Ask permission for destructive actions
5. Report progress regularly

Respond with JSON: {{"action": "...", "tool": "...", "params": {{...}}, "reasoning": "..."}}"""

    def run(self) -> None:
        """Ejecutar loop principal del agente."""
        self.running = True
        iteration = 0

        console.print(Panel("[bold red]AGENT STARTED[/]", style="red"))

        while self.running and iteration < self.max_iterations:
            iteration += 1
            if self.verbose:
                console.print(f"[dim]Iteration {iteration}[/]")

            # Obtener historial de memoria
            history = self.memory.get_history(limit=10)

            # Consultar LLM
            response = self.llm.chat(
                system=self.system_prompt,
                messages=history,
                tools=self.tools.get_schemas(),
            )

            # Procesar respuesta
            if response.get("action") == "tool_use":
                result = self._execute_tool(response)
                self.memory.add("assistant", json.dumps(response))
                self.memory.add("tool_result", json.dumps(result))
            elif response.get("action") == "final_answer":
                self._handle_final_answer(response)
                break
            else:
                self.memory.add("assistant", json.dumps(response))

            time.sleep(0.5)  # Rate limiting

        console.print(Panel("[bold red]AGENT STOPPED[/]", style="red"))

    def _execute_tool(self, response: dict[str, Any]) -> dict[str, Any]:
        """Ejecutar herramienta seleccionada."""
        tool_name = response.get("tool", "")
        params = response.get("params", {})
        
        if self.verbose:
            console.print(f"[yellow]Executing:[/] {tool_name}")

        try:
            result = self.tools.execute(tool_name, **params)
            if self.verbose:
                console.print(f"[green]✓[/] {tool_name} completed")
            return {"status": "success", "result": result}
        except Exception as e:
            console.print(f"[red]✗[/] {tool_name} failed: {e}")
            return {"status": "error", "error": str(e)}

    def _handle_final_answer(self, response: dict[str, Any]) -> None:
        """Manejar respuesta final."""
        answer = response.get("answer", "No answer provided")
        console.print(Panel(f"[bold green]RESULT:[/]\n{answer}", style="green"))
        self.memory.save_session()

    def stop(self) -> None:
        """Detener agente."""
        self.running = False

    def load_rules(self, rules_file: str) -> None:
        """Cargar Rules of Engagement."""
        import yaml
        with open(rules_file) as f:
            rules = yaml.safe_load(f)
        self.system_prompt += f"\n\nRULES OF ENGAGEMENT:\n{json.dumps(rules, indent=2)}"