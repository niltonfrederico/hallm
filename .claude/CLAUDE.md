# CLAUDE.md — hallm

## Project overview

`hallm` is a Python 3.14 Typer CLI that manages a local k3d cluster and its
services (Postgres 17, Gitea, Paperless, RustFS, ...). The CLI itself is
stateless — it orchestrates the cluster via `kubectl`/`docker`/`k3d`; service
data lives in the cluster's PersistentVolumes.

## Tech stack quick-reference

| Concern | Tool | Notes |
| --- | --- | --- |
| Runtime | Python 3.14 | Use modern syntax: `X \| Y` unions, `type` aliases, match/case |
| Package manager | uv | `uv add`, `uv sync`, never pip directly |
| Type checker | ty | Run via `uv run ty check` |
| Linter / formatter | Ruff | Run via `uv run ruff check --fix && uv run ruff format` |
| CLI | Typer | Commands live in `hallm/cli/` |
| Config | Environs | All settings come from `Settings` in `core/settings.py` |
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
│       ├── cluster/             # lifecycle: preflight/diagnose/mount/setup/nuke/healthcheck/start/stop
│       ├── db.py                # bootstrap (per-service DB creation)
│       ├── secrets.py           # apply, prepare, password, token, get-certificate
│       ├── network.py           # apply, health (dnsmasq)
│       ├── headlamp.py          # sync
│       ├── signoz.py            # bootstrap (gated by SIGNOZ_ENABLED)
│       └── container.py         # publish, deploy, remove
├── core/
│   ├── settings.py              # Class-level env reads + cached_property repo paths
│   ├── _http.py                 # BaseAsyncHTTPClient (paperless + gotify)
│   ├── gotify.py / paperless.py # gotify gated by GOTIFY_ENABLED (default True)
│   ├── cache.py                 # Async Valkey/Redis wrapper
│   ├── storage.py               # Async S3 (RustFS) helpers
│   └── enums.py
k8s/                             # Kubernetes manifests applied by `hallm cluster setup`
network/                         # dnsmasq config for *.hallm.local (`hallm network apply`)
tests/                           # Mirror of hallm/ layout
```

## Settings pattern

`hallm/core/settings.py` exposes a single `Settings` class:

- **Class-level** attributes are evaluated at module import. All env-driven
  values with sensible defaults live here (RustFS, Valkey, Paperless,
  Spotify, `DOCKER_CONTEXT`, `environment`, `debug`).
- **Feature flags** (`signoz_enabled`) default to `False`;
  `gotify_enabled` defaults to `True`. Archived manifests live under
  `k8s/archived/`; set the matching env var and restore the manifest to
  re-enable an integration (or flip the flag off without removing the
  manifest to keep the service deployed but the client wiring dormant).
- **`@cached_property`** is used for the workspace-bound paths
  (`repo_root`, `k8s_path`, `docker_path`, `network_path`). They resolve
  lazily via `hallm.core.workspace`, so importing settings never requires a
  checkout — only accessing those attributes does.
- Path constants (`PROJECT_PATH`, `SECRETS_PATH`, ...) are class-level and
  derived from `__file__`.

Always use the module-level `settings` singleton in production code:
`from hallm.core.settings import settings`.

## Persistent storage (PVs)

Service state lives in the cluster's PersistentVolumes. There are two
storage classes, chosen by **whether the data must survive a cluster
recreate**:

- **`hallm-static`** — static PV + PVC pair per stateful service, declared
  in the service's own manifest. The PV pins a fixed `hostPath` under
  `/var/lib/rancher/k3s/storage/static/<pvc-name>` (which is the SSD bind
  mount, `/mnt/hallm/static/<pvc-name>` on the host) with
  `persistentVolumeReclaimPolicy: Retain` and an explicit `claimRef`. Because
  the path is fixed (not a per-PVC UUID), the data **survives `nuke` +
  `setup`** — the re-applied PV rebinds to the same dir. Use this for any
  data you'd hate to lose (postgres, gitea, paperless, rustfs, sure, gotify,
  jupyter, leantime, immich-postgres).
- **`local-path`** — the dynamic provisioner, for **ephemeral** data only.
  A recreate orphans the old per-UUID dir and provisions a fresh empty one.
  Reserved for caches and disposable state: `valkey-data`,
  `jellyfin-cache`, `immich-model-cache`.

`shared-volumes` (RWX, on the `powah` partition) and `config-volumes` are
their own static classes — see `k8s/shared-volumes.yaml`.

When adding a stateful service, follow the static PV+PVC shape from
`k8s/postgres.yaml`; never use `local-path` for data that must persist.

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
uv sync                                # install / refresh deps
uv tool install --editable .           # install hallm globally (first time only)
uv run hallm                           # show CLI help (from inside the repo)
hallm                                  # show CLI help (anywhere, after the global install)
hallm install                          # re-run uv tool install --editable + record ~/.hallm/repo
docker compose --profile test run --rm tests              # run unit tests (≥ 98 % branch coverage)
docker compose --profile test run --rm integration-tests  # run integration tests
docker compose --profile lint run --rm lint               # run linters and formatters
docker compose up postgres -d    # start Postgres only
docker compose up --build        # full stack
```

### Working outside the repo

After `hallm install`, the CLI is on `$PATH` everywhere. Workspace-bound
commands locate the active checkout in this order:

1. `$HALLM_REPO` env var.
2. Walk-up from cwd — the first ancestor whose `pyproject.toml` declares
   `name = "hallm"` wins.
3. `~/.hallm/repo` (a text file with the absolute path — written by
   `hallm install`).

Commands that work from any cwd, with or without a discoverable repo:
`cluster preflight`, `cluster nuke`, `secrets get-certificate`, `secrets apply`,
and `container publish/deploy/remove` when a manifest/Dockerfile **path** is
passed instead of a name. `cluster healthcheck` skips smoke tests with a notice
when no checkout is found.

Commands that require a discoverable repo: `cluster setup`, `network apply`,
`db bootstrap`, `signoz bootstrap`, and any `container deploy/remove <name>`
form (which resolves against `$repo/k8s/<name>.yaml`).

## Local Kubernetes cluster (cluster namespace)

The repo includes a `k8s/` directory with Kubernetes manifests for the local
dev environment. The CLI namespace is `hallm cluster` — it covers the cluster
lifecycle: preflight/diagnose/mount/setup/nuke/healthcheck/start/stop. Secret
syncing lives under `hallm secrets apply`, cert export under
`hallm secrets get-certificate`, and per-service teardown under
`hallm container remove`.

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

Before the first `hallm cluster setup`, run the install script once:

```bash
./scripts/install-rootless-docker.sh   # idempotent; safe to re-run
# Re-login (or reboot) so cgroup delegation and render/video groups apply.
uv run hallm cluster preflight         # verify everything is in place
```

The context name is configurable via `HALLM_DOCKER_CONTEXT` (default `hallm`).

### CLI commands

```bash
# Cluster lifecycle (hallm cluster)
uv run hallm cluster preflight    # verify rootless Docker, cgroups, GPU, storage
uv run hallm cluster setup        # create cluster + Cerberus CA + service manifests
uv run hallm cluster healthcheck  # cluster + GPU + Cerberus + ports + smoke tests
uv run hallm cluster diagnose     # collect cluster diagnostics
uv run hallm cluster mount        # mount the storage device for PVC data
uv run hallm cluster nuke         # delete the cluster (add --volumes to wipe PVC data)
uv run hallm cluster start        # start the stopped cluster
uv run hallm cluster stop         # stop the cluster without deleting it

# Secrets + per-service operations
uv run hallm secrets apply            # apply ~/.hallm/*.env as Kubernetes Secrets
uv run hallm secrets get-certificate  # save Cerberus CA cert+key to ~/.hallm/
uv run hallm container remove <name>  # delete a manifest + sweep app-labelled resources
```

### k8s/ file layout

```text
k8s/
├── cerberus.yaml         # Cerberus PKI: bootstrap ClusterIssuer, root CA, CA ClusterIssuer
├── <service>.yaml        # One file per deployable service (postgres, valkey, ...)
├── archived/             # Disabled integrations (glitchtip, ots, signoz-*, wakapi)
│   └── helm/             # Archived helm values (signoz-values.yaml, k8s-infra-values.yaml)
└── test/
    ├── gpu-smoke.yaml    # one-shot Pod requesting amd.com/gpu — used by healthcheck
    └── dns-smoke.yaml    # nginx Deployment + Service + Ingress for test.hallm.local
```

Manifests under `k8s/archived/` are preserved for future revival but not
applied by `hallm cluster setup`. Move a manifest back to `k8s/` and flip the
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

`network/` holds the host-level dnsmasq config that resolves `*.hallm.local`
to the k3d cluster's Traefik.

| Concern | Detail |
| --- | --- |
| DNS | dnsmasq maps `hallm.local` → `127.0.0.1` (the cluster's Traefik) |
| Resolver wiring | `apply` points NetworkManager's active Ethernet/Wi-Fi connection at `127.0.0.1` first |
| Install mode | `install -m 0644` (copy, not symlink) — repo edits require re-running `apply` |

### Network CLI commands

```bash
uv run hallm network apply     # install dnsmasq config to /etc + reload dnsmasq (sudo)
uv run hallm network health    # binaries, service, drift, DNS resolution
```

### network/ file layout

```text
network/
└── dnsmasq.d                   # → /etc/dnsmasq.d/hallm.conf
```

## Adding a new CLI command

1. Add a `@app.command()` function in an existing subcommand file or create a new one and register it via `app.add_typer(...)` in `hallm/cli/main.py`.
2. Set `no_args_is_help=True` on the new sub-Typer so `hallm <namespace>` with no command shows help.
3. Keep business logic out of the CLI layer — delegate to `core/`.
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
