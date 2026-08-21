"""Tools - Sistema de herramientas del agente."""

from __future__ import annotations
from typing import Any
from decepticon_cli.tools.base import BaseTool, ToolRegistry
from decepticon_cli.tools.recon import ReconTools
from decepticon_cli.tools.exploit import ExploitTools

__all__ = ["BaseTool", "ToolRegistry", "ReconTools", "ExploitTools"]