# Copilot Instructions — hallm

See `.claude/CLAUDE.md` for the full project reference (tech stack, conventions, file layout, database schema, and common commands).

## Pre-commit hooks

Whenever you modify `.pre-commit-config.yaml`, run:

```bash
pre-commit autoupdate
```

This pins every hook to its latest release tag. Do this before committing the config change.

## Local Kubernetes cluster (k3d)

The repo runs a k3d cluster named `hallm` for local development. Key facts:

- **GPU**: AMD RX 6600 (RDNA2). Any pod using the GPU must set `HSA_OVERRIDE_GFX_VERSION=10.3.0` and request `amd.com/gpu: "1"`.
- **TLS**: cert-manager is installed. Use `cert-manager.io/cluster-issuer: cerberus-ca` on Ingress resources to get a locally-signed certificate.
- **DNS**: `*.hallm.local` resolves to localhost via dnsmasq.
- **Manifests**: cluster-level resources live in `k3d/`; smoke-test manifests live in `k3d/test/`.

```bash
uv run hallm k3d setup        # provision cluster
uv run hallm k3d healthcheck  # verify cluster health + run smoke tests
uv run hallm k3d nuke         # destroy cluster
```

## QA requirement

**After completing every request**, run the `qa` skill (or `/qa` prompt) to execute the full quality gate. Steps are defined in `.github/skills/qa/SKILL.md`.
