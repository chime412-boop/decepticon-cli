"""Config - Gestión de configuración con Pydantic Settings."""

from __future__ import annotations
import json
from pathlib import Path
from pydantic_settings import BaseSettings


CONFIG_DIR = Path.home() / ".config" / "decepticon"
CONFIG_FILE = CONFIG_DIR / "config.json"


class Settings(BaseSettings):
    """Configuración del agente."""
    model: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    verbose: bool = False
    max_iterations: int = 50
    sandbox_host: str = "localhost"
    sandbox_port: int = 9999

    class Config:
        env_prefix = "DECEPTICON_"


class ConfigManager:
    """Gestor de configuración persistente."""

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
        return {}

    def _save(self) -> None:
        CONFIG_FILE.write_text(json.dumps(self._data, indent=2))

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._save()

    def list_all(self) -> dict:
        return self._data.copy()