# k8s recipe

Generate a Kubernetes manifest ("recipe") for a service or job in this repo, following the conventions in `CLAUDE.md` and the existing files in `k8s/`. Then commit it.

## Argument

The user supplies a free-form description of what they want, e.g.:
`/k8s deployment para grafana, porta 3000, ingress em grafana.hallm.local, usar PVC de 5Gi`
`/k8s job para rodar migrations do paperless`
`/k8s deploy do ollama com GPU AMD`

Argument: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user what recipe they want before doing anything else. Don't guess.

## Steps

### 1. Understand the request

- Restate in one sentence what you understood, in plain text, before touching files (per memory: narrate reasoning).
- Identify: service/job name, image, ports, env vars (literal vs. secret), volumes/PVCs, ingress hostname, GPU need, resource hints.
- If anything load-bearing is missing (e.g. image tag, hostname, secret keys), ask before generating. Don't invent secret keys that don't exist in `hallm-env`.

### 2. Survey existing recipes for patterns

Always read at least:

- `k8s/paperless.yaml` — canonical Deployment + Service + Ingress (TLS via Cerberus)
- `k8s/postgres.yaml` — Deployment + PVC + Service + IngressRouteTCP
- `k8s/paperless.yaml` — multi-component app (web + sidecars) sharing labels
- `k8s/jobs/db-bootstrap.yaml` — Job pattern (backoffLimit, ttlSecondsAfterFinished, restartPolicy: Never)

Pick the closest match and adapt it. Do not copy comments or fields that don't apply.

### 3. Apply hallm conventions

Hard rules — do not deviate without asking:

- **Namespace:** `default` unless the user says otherwise.
- **Labels:** `app: <name>`; for multi-component apps add `component: <web|worker|...>`.
- **Secrets:** use `secretKeyRef` against the `hallm-env` Secret. Never hardcode credentials. If the user mentions a secret key not currently in `hallm-env`, flag it and ask.
- **Resources:** every container has `requests` and `limits` for both `cpu` and `memory`. Use modest defaults (e.g. 100m/64Mi requests, 500m/256Mi limits) unless the user gives sizing.
- **Probes:** add a `readinessProbe` (httpGet, exec, or tcpSocket) appropriate to the service.
- **Ingress (HTTP):** use this exact shape:
  ```yaml
  metadata:
    annotations:
      cert-manager.io/cluster-issuer: cerberus-ca
      traefik.ingress.kubernetes.io/router.entrypoints: websecure
  spec:
    tls:
      - hosts: [<name>.hallm.local]
        secretName: <name>-tls
    rules:
      - host: <name>.hallm.local
        http: { ... }
  ```
- **TCP ingress:** if the service needs raw TCP, use `traefik.io/v1alpha1 IngressRouteTCP` against an entrypoint defined in `k8s/traefik-config.yaml` (read it before adding a new entrypoint).
- **GPU workloads (AMD RX 6600):** must include
  ```yaml
  env:
    - name: HSA_OVERRIDE_GFX_VERSION
      value: "10.3.0"
  resources:
    limits:
      amd.com/gpu: "1"
  ```
  and ALSO request the gpu under `requests` is **not** correct — only `limits.amd.com/gpu`.
- **PVC:** `storageClassName: local-path`, `accessModes: [ReadWriteOnce]`.
- **Job:** `restartPolicy: Never`, `backoffLimit: 1`, `ttlSecondsAfterFinished: 600` unless user overrides.
- **Multi-doc YAML:** separate resources with `\n---\n`. Order: PVC → Deployment/Job → Service → Ingress.
- **No trailing comments explaining what kubectl resources are**; only keep a comment when there's a non-obvious *why* (see `postgres.yaml` IngressRouteTCP comment for an example of a *good* one).

### 4. Pick the destination path

- Deployments / StatefulSets / DaemonSets → `k8s/<name>.yaml`
- Jobs / CronJobs → `k8s/jobs/<name>.yaml`
- One-off bootstrap manifests → `k8s/adhoc/<name>.yaml`
- Tests / smoke pods → `k8s/test/<name>.yaml`

If a file with that name already exists, ask whether to overwrite or pick a different name.

### 5. Write the file

Use the `Write` tool. Don't run `kubectl apply` — that's the user's call (`uv run hallm k8s sync-secrets` / manual `kubectl apply -f`).

### 6. Commit the change

After writing, stage and commit:

```bash
git add k8s/<path>.yaml
fish -c "echo y | gc"
```

`gc` runs pre-commit, generates a conventional-commit message via Haiku, and reads `y/N` from stdin. Piping `y` through `fish -c` accepts the generated message.

If `gc` fails (no `ANTHROPIC_API_KEY`, network error, commitlint loop, pre-commit failure that isn't auto-fixable), fall back to a manual commit that follows the **same rules `gc` enforces** (from `~/.config/fish/functions/__smart_commit.fish`):

- Format: `type(scope): subject` then optional body after one blank line.
- `type` ∈ `build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test`. For a new k8s recipe: `feat(k8s): add <name> manifest`. For edits to an existing recipe: `feat(k8s): ...` or `fix(k8s): ...` as appropriate.
- Subject: lowercase, no trailing period, imperative ("add foo handler", not "Add foo handler"). Header ≤ 100 chars.
- Body (only if non-obvious): hard-wrap at 100 chars, ≤ 5 lines, explain *why*.
- Use a HEREDOC to preserve formatting:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat(k8s): add <name> manifest
  EOF
  )"
  ```
- Do **not** pass `--no-verify`. If pre-commit edits files, re-stage and create a *new* commit (never amend).

### 7. Report back

One or two sentences: file written, commit sha (or "commit aborted by user" / "commit failed: <reason>"). No re-summary of the YAML — the user can read the diff.

## Don'ts

- Don't `kubectl apply`. Don't restart the cluster.
- Don't invent env-var keys in `hallm-env` that don't exist; ask first.
- Don't add comments that describe *what* kubectl resources do.
- Don't push to a remote.
- Don't amend prior commits.
