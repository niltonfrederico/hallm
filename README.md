# hallm

LLM-powered assistant exposing an MCP server and a CLI interface, backed by Postgres.

## Stack

| Layer | Tool |
| --- | --- |
| Language | Python 3.14 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) |
| CLI | [Typer](https://typer.tiangolo.com/) |
| Type checker | [ty](https://github.com/astral-sh/ty) |
| Linter / formatter | [Ruff](https://docs.astral.sh/ruff/) |
| Database | Postgres 17 |
| Tests | Pytest |
| Containers | Docker Compose |
| Local Kubernetes | k3d |
| TLS | cert-manager + self-signed CA |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.5
- Docker + Docker Compose
- [k3d](https://k3d.io/) (for the local Kubernetes cluster)

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

## Local Kubernetes cluster

The `hallm k3d` commands manage a local k3d cluster that mirrors the production environment.

```bash
uv run hallm k3d setup        # create cluster, install GPU device plugin + cert-manager, bootstrap Cerberus CA
uv run hallm k3d healthcheck  # verify cluster health and run GPU + DNS smoke tests
uv run hallm k3d nuke         # destroy the cluster
```

### What gets provisioned

| Component | Detail |
| --- | --- |
| Cluster | `hallm` (k3d / k3s) |
| GPU | AMD RX 6600 via `/dev/kfd` + `/dev/dri` — device plugin exposes `amd.com/gpu` |
| Ingress | Traefik on ports 80 / 443 |
| TLS | cert-manager + **Cerberus** self-signed CA (`cerberus-ca` ClusterIssuer) |
| DNS | `*.hallm.local` → localhost via dnsmasq |
| Namespaces | `ollama` |

### Using TLS

Annotate any Ingress with `cert-manager.io/cluster-issuer: cerberus-ca` to get a locally-signed certificate automatically.

### GPU workloads

Every pod that uses the GPU must include:

```yaml
env:
  - name: HSA_OVERRIDE_GFX_VERSION
    value: "10.3.0"
resources:
  limits:
    amd.com/gpu: "1"
```

`HSA_OVERRIDE_GFX_VERSION=10.3.0` is required because the RX 6600 (RDNA2 / GFX 10.3) is not in ROCm's official support matrix.

## Project structure

```text
hallm/
├── cli/        # Typer CLI entry-points
├── core/       # Settings and shared utilities
├── db/         # Database models and helpers
└── mcp/        # FastMCP server and tools
k3d/
├── cerberus.yaml     # Cerberus PKI manifests
└── test/             # Smoke-test manifests (GPU pod, DNS nginx)
tests/          # Pytest test suite
docker/         # Dockerfile
```

## Environment variables

See [`.env.example`](.env.example) for all supported variables.

## License

MIT
