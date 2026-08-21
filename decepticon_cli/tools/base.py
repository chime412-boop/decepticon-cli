"""Base Tool - Clase base y registry de herramientas."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Clase base para todas las herramientas."""

    name: str = "base"
    description: str = "Base tool"
    category: str = "general"

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Ejecutar la herramienta."""
        ...

    def to_schema(self) -> dict:
        """Convertir a schema compatible con LLM tool calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._get_parameters(),
            },
        }

    def _get_parameters(self) -> dict:
        """Override en subclases para definir parámetros."""
        return {"type": "object", "properties": {}, "required": []}


class ToolRegistry:
    """Registry central de herramientas."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registrar herramientas por defecto."""
        from decepticon_cli.tools.recon import ReconTools
        from decepticon_cli.tools.exploit import ExploitTools

        for tool_class in [ReconTools, ExploitTools]:
            instance = tool_class()
            for attr_name in dir(instance):
                attr = getattr(instance, attr_name)
                if isinstance(attr, BaseTool):
                    self.register(attr)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def execute(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        return tool.execute(**kwargs)

    def get_schemas(self) -> list[dict]:
        return [t.to_schema() for t in self._tools.values()]

    def list_skills(self) -> None:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Available Tools")
        table.add_column("Name", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Description")
        for tool in self._tools.values():
            table.add_row(tool.name, tool.category, tool.description)
        console.print(table)