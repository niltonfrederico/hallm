# CLAUDE.md — hallm

## Project overview

`hallm` is a Python 3.14 project that exposes an LLM-powered assistant as an MCP server (via FastMCP) with a Typer CLI, backed by Postgres 17 for persistence.

## Tech stack quick-reference

| Concern | Tool | Notes |
| --- | --- | --- |
| Runtime | Python 3.14 | Use modern syntax: `X \| Y` unions, `type` aliases, match/case |
| Package manager | uv | `uv add`, `uv sync`, never pip directly |
| Type checker | ty | Run via `uv run ty check` |
| Linter / formatter | Ruff | Run via `uv run ruff check --fix && uv run ruff format` |
| MCP server | FastMCP | Tools and resources live in `hallm/mcp/` |
| CLI | Typer | Commands live in `hallm/cli/` |
| Config | Environs | All settings come from `Settings` in `core/settings.py` |
| ORM | Tortoise ORM + asyncpg | Models in `db/models.py`; init via `db.init_db()` |
| Tests | Pytest + pytest-cov | `asyncio_mode = "auto"`; coverage floor is **98 %** |
| Debugger | ipdb | `import ipdb; ipdb.set_trace()` — never commit breakpoints |

## Coding conventions

- **Type annotations are mandatory** on all functions and methods.
- Prefer `async def` for I/O-bound operations (DB queries, LLM calls).
- All public modules must have a module-level docstring.
- Use the `Settings` class — never read `os.environ` directly.
- Keep `hallm/` as the sole importable package; test helpers stay in `tests/`.
- No commented-out code; no bare `except:` clauses.

## File layout

```text
hallm/
├── cli/
│   ├── base/                    # Subprocess + kubectl + docker + poll + template helpers
│   │   ├── shell.py             # run/run_or_fail/check/fail
│   │   ├── docker.py            # context-pinned subprocess wrappers
│   │   ├── kubectl.py           # apply/apply_url/apply_from_cmd/wait/get_json/...
│   │   ├── poll.py              # poll_until(predicate, timeout, interval)
│   │   └── template.py          # ##KEY## placeholder rendering
│   ├── main.py                  # Typer root app
│   └── subcommands/
│       ├── k8s.py               # cluster lifecycle + cluster operations
│       ├── db.py                # bootstrap (per-service DB creation)
│       ├── mcp.py               # serve
│       ├── network.py           # apply, health (Caddy + dnsmasq)
│       └── container.py         # publish
├── core/
│   ├── settings.py              # Class-level env reads + cached_property DB
│   ├── observability.py         # Glitchtip + SigNoz/OTEL bootstrap (flag-gated)
│   ├── _http.py                 # BaseAsyncHTTPClient (paperless + archived gotify)
│   ├── gotify.py / paperless.py # gotify gated by GOTIFY_ENABLED
│   ├── cache.py                 # Async Valkey/Redis wrapper
│   ├── storage.py               # Async S3 (RustFS) helpers
│   └── enums.py
├── db/
│   ├── __init__.py              # init_db()/close_db(), TORTOISE_ORM
│   ├── models.py
│   ├── base/
│   │   ├── mixins.py            # TimestampMixin
│   │   └── fields.py            # SlugField, URLField, FileField, ImageField, StoredFile
│   └── migrations/
└── mcp/                         # FastMCP server
k8s/                             # Kubernetes manifests applied by `hallm k8s setup`
network/                         # Caddyfile + dnsmasq + caddy unit template (`hallm network apply`)
tests/                           # Mirror of hallm/ layout
```

## Settings pattern

`hallm/core/settings.py` exposes a single `Settings` class:

- **Class-level** attributes are evaluated at module import. All env-driven
  values with sensible defaults live here (RustFS, Valkey, Paperless,
  OTEL, Spotify, `DOCKER_CONTEXT`, `environment`, `debug`).
- **Feature flags** (`signoz_enabled`, `glitchtip_enabled`, `gotify_enabled`)
  default to `False`. Their manifests live under `k8s/archived/`; set the
  matching env var (`SIGNOZ_ENABLED`, `GLITCHTIP_ENABLED`, `GOTIFY_ENABLED`)
  to `true` and restore the manifest to re-enable the integration.
- **`@cached_property`** is used for `database`, `database_url`, and
  `tortoise_database_url`. These have no defaults, so each `Settings()`
  instance reads them on first access — letting tests monkeypatch
  `DATABASE_*` env vars per-test.
- Path constants (`ROOT_PATH`, `K8S_PATH`, `SECRETS_PATH`, ...) are
  class-level and derived from `__file__`.

Always use the module-level `settings` singleton in production code:
`from hallm.core.settings import settings`.

## Database

### Base classes and custom fields

All models inherit from **`TimestampMixin`** (`db/base/mixins.py`):

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `UUIDField` | Primary key, auto-generated |
| `created_at` | `DatetimeField` | `auto_now_add=True` |
| `updated_at` | `DatetimeField` | `auto_now=True` |

`db/base/fields.py` provides:

- **`SlugField`** — `CharField` (max 60, nullable) that auto-slugifies via
  `python-slugify`. Pass `from_field="<other_field>"` to derive the slug
  from another field.
- **`URLField`** — `CharField` (max 2000) with `validators.url` validation.
- **`StoredFile`** + **`FileField`** — store an S3 key, expose async
  `url()`/`read()`/`delete()` helpers backed by `hallm.core.storage`.
- **`ImageField`** — `FileField` subclass that rejects non-image MIME types.

### Models

Currently: `FeatureFlag`, `Library`, `Content`, `Tag`. See `db/models.py`.

### DB initialisation

`db/__init__.py` exposes:

- `init_db()` — calls `Tortoise.init(config=TORTOISE_ORM)`.
- `close_db()` — calls `Tortoise.close_connections()`.
- `TORTOISE_ORM` — dict config used by both runtime init and `[tool.tortoise]`.

## CLI helpers

Reuse instead of reimplementing:

- `hallm/cli/base/shell.py` — `run`, `run_or_fail`, `fail` (NoReturn), `check`.
- `hallm/cli/base/docker.py` — `run`, `run_or_fail` pinned to `DOCKER_CONTEXT`.
- `hallm/cli/base/kubectl.py` — `apply`, `apply_url`, `apply_from_cmd`,
  `get_json`, `wait`, `rollout_restart`, `delete_manifest`, `delete_by_label`.
- `hallm/cli/base/poll.py` — `poll_until(predicate, *, timeout, interval=2.0)`.
- `hallm/cli/base/template.py` — `render(text, subs)` with `##KEY##` syntax.

## HTTP clients

`hallm/core/_http.py` provides `BaseAsyncHTTPClient`. Subclasses
(`GotifyClient`, `PaperlessClient`) only override `_build_client` (auth
headers etc.) and set `_error_class`; the async-context-manager lifecycle
plus `_check(response)` come for free.

## Common commands

```bash
uv sync                          # install / refresh deps
uv run hallm                     # show CLI help
uv run hallm mcp serve           # start the MCP server
docker compose --profile test run --rm tests              # run unit tests (≥ 98 % branch coverage)
docker compose --profile test run --rm integration-tests  # run integration tests
docker compose --profile lint run --rm lint               # run linters and formatters
uv run tortoise makemigrations   # generate new migration
uv run tortoise migrate          # apply pending migrations
docker compose up postgres -d    # start Postgres only
docker compose up --build        # full stack
```

## Local Kubernetes cluster (k8s namespace)

The repo includes a `k8s/` directory with Kubernetes manifests for the local
dev environment. The CLI namespace is `hallm k8s` — it covers both cluster
lifecycle (preflight/setup/healthcheck/nuke/get-cert) and cluster operations
(sync-secrets/remove).

### Cluster overview

| Concern | Detail |
| --- | --- |
| Cluster manager | k3d (k3s in Docker) |
| Cluster name | `hallm` |
| Docker daemon | Dedicated rootless daemon, exposed via the `hallm` Docker context |
| GPU | AMD RX 6600 — mounted via `/dev/kfd` and `/dev/dri` (no `--gpus all`) |
| Ingress | Traefik on ports 80 / 443, exposed via k3d loadbalancer |
| TLS | cert-manager + Cerberus self-signed CA (`cerberus-ca` ClusterIssuer) |
| DNS | `*.hallm.local` resolves to localhost via dnsmasq |
| Namespaces | `docs` (and `signoz` when `SIGNOZ_ENABLED=true`) |

### Rootless Docker prerequisites

The cluster runs on a **dedicated rootless Docker daemon** so the user's
default Docker daemon stays untouched. Every `k3d` and `docker` invocation
from the hallm CLI is pinned to the `hallm` Docker context via the
`DOCKER_CONTEXT` env var — see `hallm/cli/base/docker.py`.

Before the first `hallm k8s setup`, run the install script once:

```bash
./scripts/install-rootless-docker.sh   # idempotent; safe to re-run
# Re-login (or reboot) so cgroup delegation and render/video groups apply.
uv run hallm k8s preflight             # verify everything is in place
```

The context name is configurable via `HALLM_DOCKER_CONTEXT` (default `hallm`).

### CLI commands

```bash
# Cluster lifecycle
uv run hallm k8s preflight    # verify rootless Docker, cgroups, GPU, storage
uv run hallm k8s setup        # create cluster + Cerberus CA + service manifests
uv run hallm k8s healthcheck  # cluster + GPU + Cerberus + ports + smoke tests
uv run hallm k8s nuke         # delete the cluster (add --volumes to wipe PVC data)
uv run hallm k8s get-cert     # save Cerberus CA cert+key to ~/.hallm/

# Cluster operations
uv run hallm k8s sync-secrets    # apply ~/.hallm/*.env as Kubernetes Secrets
uv run hallm k8s remove <name>   # delete a manifest + sweep app-labelled resources
```

### k8s/ file layout

```text
k8s/
├── cerberus.yaml         # Cerberus PKI: bootstrap ClusterIssuer, root CA, CA ClusterIssuer
├── <service>.yaml        # One file per deployable service (postgres, valkey, ...)
├── archived/             # Disabled integrations (glitchtip, gotify, ots, signoz-*, wakapi)
│   └── helm/             # Archived helm values (signoz-values.yaml, k8s-infra-values.yaml)
└── test/
    ├── gpu-smoke.yaml    # one-shot Pod requesting amd.com/gpu — used by healthcheck
    └── dns-smoke.yaml    # nginx Deployment + Service + Ingress for test.hallm.local
```

Manifests under `k8s/archived/` are preserved for future revival but not
applied by `hallm k8s setup`. Move a manifest back to `k8s/` and flip the
matching feature flag to re-enable a service.

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

`HSA_OVERRIDE_GFX_VERSION=10.3.0` is required because the RX 6600 (GFX 10.3 / RDNA2) is not in ROCm's official support matrix.

### TLS / Ingress

Annotate any Ingress with `cert-manager.io/cluster-issuer: cerberus-ca` to get a certificate signed by the local CA. Add `cerberus-ca-secret` to your browser/OS trust store if you need the cert to be trusted locally.

## Local network (network/ + `hallm network`)

`network/` holds the host-level config that fronts the OpenClaw gateway and
any future `*.hallm.local` services that don't live in the k3d cluster.

| Concern | Detail |
| --- | --- |
| Reverse proxy | Caddy bound to `127.0.0.2:80` (kept off `127.0.0.1` to avoid the cluster's Traefik) |
| DNS | dnsmasq maps `openclaw.hallm.local` → `127.0.0.2`, `hallm.local` → `127.0.0.1` |
| Backend | OpenClaw gateway on `127.0.0.1:18789` (source: `~/.openclaw/openclaw.json` → `gateway.port`) |
| Caddy runtime | System systemd unit `hallm-caddy.service`, root-owned (so `:80` works without caps) |
| Install mode | `install -m 0644` (copy, not symlink) — repo edits require re-running `apply` |

### Network CLI commands

```bash
uv run hallm network apply     # install configs to /etc + (re)load caddy & dnsmasq (sudo)
uv run hallm network health    # binaries, services, drift, DNS, TCP reachability
```

### network/ file layout

```text
network/
├── Caddyfile                   # → /etc/caddy/Caddyfile
├── dnsmasq.d                   # → /etc/dnsmasq.d/hallm.conf
└── hallm-caddy.service.tpl     # rendered with ##CADDY_BIN##, → /etc/systemd/system/hallm-caddy.service
```

If you change the OpenClaw gateway port, update **both** `network/Caddyfile`
and `~/.openclaw/openclaw.json`, then re-run `hallm network apply`.

## Adding a new model

1. Inherit from `TimestampMixin` (not `Model` directly).
2. Define fields in `hallm/db/models.py`.
3. Use `SlugField(from_field="name")` when a slug should mirror another field.
4. Run `uv run tortoise makemigrations` then `uv run tortoise migrate`.

## Adding a new MCP tool

1. Add a function decorated with `@mcp.tool()` inside `hallm/mcp/server.py` (or a submodule imported there).
2. All parameters must be typed and documented via docstring.
3. Add a test in `tests/hallm/mcp/`.

## Adding a new CLI command

1. Add a `@app.command()` function in an existing subcommand file or create a new one and register it via `app.add_typer(...)` in `hallm/cli/main.py`.
2. Set `no_args_is_help=True` on the new sub-Typer so `hallm <namespace>` with no command shows help.
3. Keep business logic out of the CLI layer — delegate to `core/` or `mcp/`.
4. Reuse helpers from `hallm/cli/base/` instead of calling `subprocess` directly.

## Test coverage

`pyproject.toml` enforces **`fail_under = 98`** for branch coverage. New code
must be tested. Targets:

- CLI subcommands: invoke via `typer.testing.CliRunner` with `subprocess.run` patched.
- HTTP clients: use `httpx.MockTransport` to intercept calls.
- S3 / Redis: patch `aioboto3.Session` / `redis.asyncio.Redis.from_url`.

## Pre-commit hooks

@.claude/rules/pre-commit.md

## Pull request checklist

- [ ] `docker compose --profile lint run --rm lint` passes
- [ ] `docker compose --profile test run --rm tests` passes (coverage ≥ 98 %)
- [ ] New code has type annotations
- [ ] No hardcoded secrets or credentials
