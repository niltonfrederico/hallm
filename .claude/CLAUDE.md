# CLAUDE.md — hallm

## Project overview

`hallm` is a Python 3.14 project that exposes an LLM-powered assistant as an MCP server (via FastMCP) with a Typer CLI. It uses LiteLLM for model-agnostic LLM calls and Postgres 17 for persistence.

## Tech stack quick-reference

| Concern | Tool | Notes |
| --- | --- | --- |
| Runtime | Python 3.14 | Use modern syntax: `X \| Y` unions, `type` aliases, match/case |
| Package manager | uv | `uv add`, `uv sync`, never pip directly |
| Type checker | ty | Run via `uv run ty check` |
| Linter / formatter | Ruff | Run via `uv run ruff check --fix && uv run ruff format` |
| LLM routing | LiteLLM | `litellm.acompletion` for async calls |
| MCP server | FastMCP | Tools and resources live in `hallm/mcp/` |
| CLI | Typer | Commands live in `hallm/cli/` |
| Config | Environs | All settings come from `Settings` in `core/settings.py` |
| ORM | Tortoise ORM + asyncpg | Models in `db/models.py`; init via `db.init_db()` |
| Tests | Pytest | Async tests use `asyncio_mode = "auto"` |
| Debugger | ipdb | `import ipdb; ipdb.set_trace()` — never commit breakpoints |

## Coding conventions

- **Type annotations are mandatory** on all functions and methods.
- Prefer `async def` for I/O-bound operations (DB queries, LLM calls).
- All public modules must have a module-level docstring.
- Use `environs` `Settings` class — never read `os.environ` directly.
- Keep `hallm/` as the sole importable package; test helpers stay in `tests/`.
- No commented-out code; no bare `except:` clauses.

## File layout

```text
hallm/
├── cli/        # Typer app and sub-commands
├── core/       # Settings, logging config, shared utils
├── db/         # DB connection, models, migrations helpers
│   ├── __init__.py       # init_db() / close_db(), TORTOISE_ORM config
│   ├── models.py         # All Tortoise models
│   ├── base/
│   │   ├── mixins.py     # TimestampMixin
│   │   └── fields.py     # SlugField
│   └── migrations/       # Tortoise migration files
└── mcp/        # FastMCP instance, tools, resources, prompts
tests/
├── conftest.py
└── <module>/   # Mirror hallm layout in tests
```

## Database

### Base classes and custom fields

All models inherit from **`TimestampMixin`** (`db/base/mixins.py`), which provides:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `UUIDField` | Primary key, auto-generated |
| `created_at` | `DatetimeField` | Set on insert (`auto_now_add=True`) |
| `updated_at` | `DatetimeField` | Updated on every save (`auto_now=True`) |

**`SlugField`** (`db/base/fields.py`) is a `CharField` (max 60 chars, nullable by default) that auto-slugifies its value using `python-slugify`. When `from_field` is set, the slug is derived from another field on the model instead of being set directly.

### Models

#### `FeatureFlag`

Manages application feature flags.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | PK (from `TimestampMixin`) |
| `name` | `CharField` | Human-readable name |
| `description` | `TextField` | Defaults to `""` |
| `slug` | `SlugField` | Unique; auto-slugified |
| `enabled` | `BooleanField` | Defaults to `False` |
| `created_at` | `DatetimeField` | From `TimestampMixin` |
| `updated_at` | `DatetimeField` | From `TimestampMixin` |

### DB initialisation

`db/__init__.py` exposes:

- `init_db()` — calls `Tortoise.init(config=TORTOISE_ORM)`. Call on app startup.
- `close_db()` — calls `Tortoise.close_connections()`. Call on app shutdown.
- `TORTOISE_ORM` — dict config used by both runtime init and `[tool.tortoise]` in `pyproject.toml`.

## Common commands

```bash
uv sync                          # install / refresh deps
uv run hallm serve               # start the MCP server
uv run pytest                    # run tests
uv run ruff check --fix && uv run ruff format  # lint + format
uv run ty check                  # type check
uv run pre-commit run --all      # full pre-commit suite
uv run tortoise init             # create migrations package (first time)
uv run tortoise makemigrations   # generate new migration from model changes
uv run tortoise migrate          # apply pending migrations
uv run tortoise downgrade models 0001_initial  # roll back a migration
uv run tortoise history          # list applied migrations
docker compose up db -d          # start Postgres only
docker compose up --build        # full stack
docker compose --profile lint run lint  # run pre-commit via Docker
```

## Local Kubernetes cluster (k3d)

The repo includes a `k3d/` directory with Kubernetes manifests for the local dev environment.

### Cluster overview

| Concern | Detail |
| --- | --- |
| Cluster manager | k3d (k3s in Docker) |
| Cluster name | `hallm` |
| GPU | AMD RX 6600 — mounted via `/dev/kfd` and `/dev/dri` (no `--gpus all`) |
| Ingress | Traefik on ports 80 / 443, exposed via k3d loadbalancer |
| TLS | cert-manager + Cerberus self-signed CA (`cerberus-ca` ClusterIssuer) |
| DNS | `*.hallm.local` resolves to localhost via dnsmasq |
| Namespaces | `ollama` |

### CLI commands

```bash
uv run hallm k3d setup        # create cluster, install device plugin + cert-manager + Cerberus CA, create ollama namespace
uv run hallm k3d healthcheck  # verify cluster, GPU, Cerberus issuer, ports, and run GPU + DNS smoke tests
uv run hallm k3d nuke         # delete the cluster (prompts for confirmation; use --yes to skip)
```

### k3d/ file layout

```text
k3d/
├── cerberus.yaml     # Cerberus PKI: bootstrap ClusterIssuer, root CA Certificate, CA ClusterIssuer
└── test/
    ├── gpu-smoke.yaml   # one-shot Pod that requests amd.com/gpu: "1" — used by healthcheck
    └── dns-smoke.yaml   # nginx Deployment + Service + Ingress for test.hallm.local — used by healthcheck
```

### GPU workloads

Any Deployment that uses the GPU **must** set:

```yaml
env:
  - name: HSA_OVERRIDE_GFX_VERSION
    value: "10.3.0"
resources:
  limits:
    amd.com/gpu: "1"
```

`HSA_OVERRIDE_GFX_VERSION=10.3.0` is required because the RX 6600 (GFX 10.3 / RDNA2) is not in ROCm's official support matrix; this env var forces the correct architecture detection.

### TLS / Ingress

Annotate any Ingress with `cert-manager.io/cluster-issuer: cerberus-ca` to get a certificate signed by the local CA. The CA is self-signed; add `cerberus-ca-secret` to your browser/OS trust store if you need the cert to be trusted locally.

## Adding a new model

1. Inherit from `TimestampMixin` (not `Model` directly).
2. Define fields in `hallm/db/models.py`.
3. Use `SlugField(from_field="name")` when a slug should mirror another field.
4. Run `uv run tortoise makemigrations` then `uv run tortoise migrate`.

## Adding a new MCP tool

1. Add a function decorated with `@mcp.tool()` inside `hallm/mcp/server.py` (or a submodule imported there).
2. All parameters must be typed and documented via docstring.
3. Add a test in `tests/mcp/`.

## Adding a new CLI command

1. Add a `@app.command()` function in `hallm/cli/main.py` or a new file, then register it with `app.add_typer(...)`.
2. Keep business logic out of the CLI layer — delegate to `core/` or `mcp/`.

## Pre-commit hooks

@.claude/rules/pre-commit.md

## Pull request checklist

- [ ] `uv run pre-commit run --all` passes
- [ ] `uv run pytest` passes
- [ ] New code has type annotations
- [ ] No hardcoded secrets or credentials
