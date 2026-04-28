# hallm

LLM-powered assistant exposing an MCP server and a CLI interface, backed by Postgres.

## Stack

| Layer | Tool |
|-------|------|
| Language | Python 3.14 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| LLM routing | [LiteLLM](https://docs.litellm.ai/) |
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) |
| CLI | [Typer](https://typer.tiangolo.com/) |
| Type checker | [ty](https://github.com/astral-sh/ty) |
| Linter / formatter | [Ruff](https://docs.astral.sh/ruff/) |
| Database | Postgres 17 |
| Tests | Pytest |
| Containers | Docker Compose |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.5
- Docker + Docker Compose

### Local setup

```bash
# Clone and enter the repo
git clone <repo-url> && cd hallm

# Copy env vars and edit as needed
cp .env.example .env

# Create venv and install deps (including dev)
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Start Postgres
docker compose up db -d

# Run migrations
uv run tortoise migrate

# Run the MCP server
uv run hallm serve
```

### Running tests

```bash
uv run pytest
```

### Running the full stack with Docker

```bash
docker compose up --build
```

## Project structure

```
src/hallm/
├── cli/        # Typer CLI entry-points
├── core/       # Settings and shared utilities
├── db/         # Database models and helpers
└── mcp/        # FastMCP server and tools
tests/          # Pytest test suite
docker/         # Dockerfile
```

## Environment variables

See [`.env.example`](.env.example) for all supported variables.

## License

MIT
