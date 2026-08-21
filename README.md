# Decepticon CLI Agent Harness

Agente autónomo CLI para pentesting con IA. Framework ligero para crear agentes de seguridad.

## Instalación

`ash
pip install decepticon-cli
`

## Uso

`ash
# Iniciar agente
decepticon start

# Configurar
decepticon config set OPENAI_API_KEY sk-xxx

# Ejecutar engagement
decepticon engage --target 192.168.1.0/24
`

## Arquitectura

`
decepticon-cli/
├── decepticon_cli/
│   ├── __init__.py
│   ├── __main__.py      # Entry point
│   ├── cli.py           # CLI commands (typer)
│   ├── agent.py         # Core agent loop
│   ├── llm.py           # LLM provider abstraction
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py      # Tool base class
│   │   ├── recon.py     # Reconnaissance tools
│   │   └── exploit.py   # Exploitation tools
│   ├── config.py        # Configuration management
│   └── memory.py        # Agent memory
├── pyproject.toml
└── README.md
`

## Stack

- **CLI**: Typer
- **LLM**: LiteLLM (multi-provider)
- **Memory**: SQLite
- **Config**: Pydantic Settings