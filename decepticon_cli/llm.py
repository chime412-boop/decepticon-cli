"""LLM Provider - Abstracción multi-provider via LiteLLM."""

from __future__ import annotations
import json
from typing import Any
import litellm
from decepticon_cli.config import ConfigManager

litellm.drop_params = True  # Ignorar parámetros no soportados


class LLMProvider:
    """Proveedor LLM multi-backend."""

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.1):
        self.model = model
        self.temperature = temperature
        self.config = ConfigManager()
        
        # Configurar API keys desde config
        self._setup_credentials()

    def _setup_credentials(self) -> None:
        """Configurar credenciales desde config manager."""
        providers = {
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
            "GOOGLE_API_KEY": "gemini",
            "DEEPSEEK_API_KEY": "deepseek",
        }
        for env_key, provider in providers.items():
            key = self.config.get(env_key.lower())
            if key:
                import os
                os.environ[env_key] = key

    def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Enviar mensaje al LLM y procesar respuesta."""
        formatted_messages = [{"role": "system", "content": system}]
        formatted_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = litellm.completion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            return {"action": "error", "error": str(e)}

    def _parse_response(self, response: Any) -> dict[str, Any]:
        """Parsear respuesta del LLM a formato interno."""
        choice = response.choices[0]
        message = choice.message

        # Si hay tool calls
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            return {
                "action": "tool_use",
                "tool": tool_call.function.name,
                "params": args,
                "reasoning": message.content or "",
            }

        # Respuesta de texto normal
        content = message.content or ""
        
        # Intentar parsear como JSON (agente mode)
        try:
            parsed = json.loads(content)
            if "action" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        return {"action": "final_answer", "answer": content}