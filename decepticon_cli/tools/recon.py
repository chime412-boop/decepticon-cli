"""Recon Tools - Herramientas de reconocimiento."""

from __future__ import annotations
import subprocess
import socket
from typing import Any
from decepticon_cli.tools.base import BaseTool


class PortScan(BaseTool):
    name = "port_scan"
    description = "Scan common ports on a target host"
    category = "recon"

    def execute(self, host: str = "", ports: str = "1-1000", **kwargs: Any) -> dict:
        open_ports = []
        port_range = self._parse_range(ports)
        
        for port in port_range[:100]:  # Limit for safety
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((host, port))
                if result == 0:
                    open_ports.append(port)
                sock.close()
            except Exception:
                pass
        
        return {"host": host, "open_ports": open_ports, "scanned": len(port_range[:100])}

    def _parse_range(self, ports: str) -> list[int]:
        if "-" in ports:
            start, end = ports.split("-")
            return list(range(int(start), int(end) + 1))
        return [int(p.strip()) for p in ports.split(",")]

    def _get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Target IP address"},
                "ports": {"type": "string", "description": "Port range (e.g., 1-1000)"},
            },
            "required": ["host"],
        }


class ServiceEnum(BaseTool):
    name = "service_enum"
    description = "Enumerate services on open ports"
    category = "recon"

    def execute(self, host: str = "", port: int = 80, **kwargs: Any) -> dict:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            
            # Try HTTP header
            sock.send(b"HEAD / HTTP/1.0\r\nHost: " + host.encode() + b"\r\n\r\n")
            banner = sock.recv(1024).decode(errors="ignore")
            sock.close()
            
            return {"host": host, "port": port, "banner": banner[:500]}
        except Exception as e:
            return {"host": host, "port": port, "error": str(e)}

    def _get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Target IP"},
                "port": {"type": "integer", "description": "Port number"},
            },
            "required": ["host", "port"],
        }


class ReconTools:
    """Agrupación de herramientas de reconocimiento."""
    port_scan = PortScan()
    service_enum = ServiceEnum()