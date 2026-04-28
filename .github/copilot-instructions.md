# Copilot Instructions — hallm

## Project overview

`hallm` is a Python 3.14 project that exposes an LLM-powered assistant as an MCP server (via FastMCP) with a Typer CLI. It uses LiteLLM for model-agnostic LLM calls and Postgres 17 for persistence.

## Tech stack quick-reference

| Concern | Tool | Notes |
|---------|------|-------|
| Runtime | Python 3.14 | Use modern syntax: `X \| Y` unions, `type` aliases, match/case |
| Package manager | uv | `uv add`, `uv sync`, never pip directly |
| Type checker | ty | Run via `uv run ty check` |
| Linter / formatter | Ruff | Run via `uv run ruff check --fix && uv run ruff format` |
| LLM routing | LiteLLM | `litellm.acompletion` for async calls |
| MCP server | FastMCP | Tools and resources live in `src/hallm/mcp/` |
| CLI | Typer | Commands live in `src/hallm/cli/` |
| Config | Environs | All settings come from `Settings` in `core/settings.py` |
| ORM | Tortoise ORM + asyncpg | Models in `db/models.py`; init via `db.init_db()` |
| Tests | Pytest | Async tests use `asyncio_mode = "auto"` |
| Debugger | ipdb | `import ipdb; ipdb.set_trace()` — never commit breakpoints |

## Coding conventions

- **Type annotations are mandatory** on all functions and methods.
- Prefer `async def` for I/O-bound operations (DB queries, LLM calls).
- All public modules must have a module-level docstring.
- Use `environs` `Settings` class — never read `os.environ` directly.
- Keep `src/hallm/` as the sole importable package; test helpers stay in `tests/`.
- No commented-out code; no bare `except:` clauses.

## File layout

```
src/hallm/
├── cli/        # Typer app and sub-commands
├── core/       # Settings, logging config, shared utils
├── db/         # DB connection, models, migrations helpers
└── mcp/        # FastMCP instance, tools, resources, prompts
tests/
├── conftest.py
└── <module>/   # Mirror src layout in tests
```

## Common commands

```bash
uv sync                          # install / refresh deps
uv run hallm serve               # start the MCP server
uv run pytest                    # run tests
uv run ruff check --fix && uv run ruff format  # lint + format
uv run ty check                  # type check
uv run pre-commit run --all-files  # full pre-commit suite
uv run tortoise init             # create migrations package (first time)
uv run tortoise makemigrations   # generate new migration from model changes
uv run tortoise migrate          # apply pending migrations
uv run tortoise downgrade models 0001_initial  # roll back a migration
uv run tortoise history          # list applied migrations
docker compose up db -d          # start Postgres only
docker compose up --build        # full stack
```

## Adding a new MCP tool

1. Add a function decorated with `@mcp.tool()` inside `src/hallm/mcp/server.py` (or a submodule imported there).
2. All parameters must be typed and documented via docstring.
3. Add a test in `tests/mcp/`.

## Adding a new CLI command

1. Add a `@app.command()` function in `src/hallm/cli/main.py` or a new file, then register it with `app.add_typer(...)`.
2. Keep business logic out of the CLI layer — delegate to `core/` or `mcp/`.

## Pull request checklist

- [ ] `uv run pre-commit run --all-files` passes
- [ ] `uv run pytest` passes
- [ ] New code has type annotations
- [ ] No hardcoded secrets or credentials
