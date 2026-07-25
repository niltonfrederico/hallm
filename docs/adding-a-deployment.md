# Adding a Deployment to a hallm cluster

End-to-end recipe to ship a new service into a local hallm cluster. Assumes no
prior knowledge of hallm.

## What hallm is

`hallm` is a local development environment that runs a single-node Kubernetes
cluster (`k3d` — k3s in Docker) on the developer's workstation. The cluster
is bootstrapped by `hallm cluster setup` and exposes:

| Thing | Value |
| --- | --- |
| Default namespace | `default` |
| Ingress | Traefik on `*.hallm.local`, TLS via Cerberus CA |
| Image registry | `unregistry.hallm.local` |
| Service-private PVCs | `storageClassName: hallm-static` (survives a cluster recreate) |
| Throwaway PVCs (caches) | `storageClassName: local-path` (wiped on recreate) |
| Host-shared PVC (RWX) | `claimName: shared-volumes` — backed by `~/.hallm/shared-volumes/` on the host |
| Secrets | `secretKeyRef: { name: hallm-env, key: <VAR> }` (synced from `~/.hallm/*.env`) |

## The four artefacts

To add a service named `myapp`, write:

1. `docker/Dockerfile.myapp` — image build recipe (skip if you use a public image).
2. `k8s/myapp.yaml` — Deployment + Service + Ingress (+ optional PVC).
3. New keys in `~/.hallm/hallm.env` if the app needs secrets.
4. (Internal-only) register a setup step — only needed if your service must be
   part of `hallm cluster setup`. Day-to-day deploys do not require this.

## Manifest template

Copy and rename. This is the minimal shape: Deployment, Service, Ingress with
TLS, and the most common storage options commented in place.

```yaml
# k8s/myapp.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: myapp
          image: unregistry.hallm.local/hallm/myapp:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
          env:
            - name: SOME_SECRET
              valueFrom:
                secretKeyRef:
                  name: hallm-env
                  key: MYAPP_SOME_SECRET
          resources:
            requests: { cpu: "100m", memory: 128Mi }
            limits:   { cpu: "1",    memory: 1Gi   }
          volumeMounts:
            # Pick zero, one, or both of these:
            - name: data           # service-private storage
              mountPath: /var/lib/myapp
            - name: shared         # host-shared scratch space
              mountPath: /data
              subPath: myapp       # → ~/.hallm/shared-volumes/myapp/
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: myapp-data
        - name: shared
          persistentVolumeClaim:
            claimName: shared-volumes   # pre-existing, RWX, do not redeclare

---
# Only if you mounted `data` above. A static PV+PVC *pair*, not a bare PVC:
# the PV pins a fixed hostPath, so `hallm cluster nuke` + `setup` rebinds to the
# same directory instead of provisioning a fresh empty one. See "Storage decision".
apiVersion: v1
kind: PersistentVolume
metadata:
  name: myapp-data
  labels:
    app: myapp
spec:
  capacity:
    storage: 5Gi
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: hallm-static
  hostPath:
    path: /var/lib/rancher/k3s/storage/static/myapp-data
    type: DirectoryOrCreate
  claimRef:                      # binds this PV to that exact PVC, nothing else
    namespace: default
    name: myapp-data

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: myapp-data
  namespace: default
  labels:
    app: myapp                   # required — hallm container remove sweeps by this label
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: hallm-static
  resources:
    requests:
      storage: 5Gi
  volumeName: myapp-data         # the other half of the claimRef pairing

---
apiVersion: v1
kind: Service
metadata:
  name: myapp
  namespace: default
spec:
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 8080

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: default
  annotations:
    cert-manager.io/cluster-issuer: cerberus-ca
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
spec:
  tls:
    - hosts: [myapp.hallm.local]
      secretName: myapp-tls
  rules:
    - host: myapp.hallm.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp
                port:
                  number: 80
```

## Storage decision

The class is chosen by one question: **must this data survive a cluster
recreate?**

| Need | Use |
| --- | --- |
| Service-private files you'd hate to lose (db, app state) | Static PV+PVC pair, `storageClassName: hallm-static` |
| Caches and disposable state | New PVC, `storageClassName: local-path`, `accessModes: ReadWriteOnce` |
| Files visible on the host or shared between pods | `claimName: shared-volumes` (exists already) + `subPath: <unique>` |
| Ephemeral scratch, lost on pod restart | `emptyDir: {}` |
| Read-only config (small, non-secret) | `ConfigMap` mounted as volume |
| Object storage (S3 API) | RustFS at `s3.hallm.local` (no PVC needed) |

### Why `local-path` is not the default

`local-path` is the dynamic provisioner: it carves a fresh directory per PVC
UUID under `/var/lib/rancher/k3s/storage/`. Delete and recreate the cluster and
the PVC gets a **new** UUID — the old directory is orphaned on disk and the pod
comes up against an empty volume. The data is still there, but nothing points
at it.

`hallm-static` avoids that by pinning a fixed `hostPath` keyed on the PVC name
(`/var/lib/rancher/k3s/storage/static/<pvc-name>`, which is the SSD bind mount
`/mnt/hallm/static/<pvc-name>` on the host) with `Retain` and an explicit
`claimRef`. Re-applying the manifest after a `nuke` rebinds to the same
directory, with the same data.

### About `shared-volumes`

A pre-installed `ReadWriteMany` PVC backed by the host directory
`~/.hallm/shared-volumes/`. **Always mount it with a `subPath`** — otherwise
two pods stomp on each other and on the host's other files. The subPath
auto-creates on first mount.

Use it for: dev-time artefact exchange, host-visible data drops, sharing files
between two pods. Avoid it for service-private state — use `hallm-static`
instead.

## Secrets

Add a line to `~/.hallm/hallm.env`:

```bash
# ~/.hallm/hallm.env
MYAPP_SOME_SECRET=...
```

Sync into the cluster as the `hallm-env` Secret:

```bash
hallm secrets apply
```

Reference from the manifest:

```yaml
env:
  - name: SOME_SECRET
    valueFrom:
      secretKeyRef:
        name: hallm-env
        key: MYAPP_SOME_SECRET
```

## Image build

Two options.

**Public image.** Set `image: <whatever>:<tag>` in the manifest. No Dockerfile,
no publish step.

**Custom image.** Add `docker/Dockerfile.myapp`. Build context is the repo
root. Tag is fixed at `unregistry.hallm.local/hallm/myapp:latest`:

```bash
hallm container publish myapp        # builds + pushes
```

`hallm container deploy myapp` (next step) auto-builds when
`docker/Dockerfile.myapp` exists, so you usually skip the explicit publish.

## Deploy

```bash
hallm container deploy myapp
```

What this does:

1. Builds `docker/Dockerfile.myapp` (if present) and pushes to
   `unregistry.hallm.local`.
2. Runs `kubectl apply -f k8s/myapp.yaml`.
3. If step 1 built something, runs
   `kubectl rollout restart deploy -l app=myapp` — see below for why.

Pass `--no-build` to skip the rebuild when you only want to re-apply the
manifest, or when the image is public. Pass `--restart` to force a rollout
without rebuilding, `--no-restart` to suppress it, and `-n/--namespace` to
target a namespace other than `default`.

### Why the rollout restart is not optional

`kubectl apply` is **declarative**: it diffs the manifest against the live
object and does nothing when they match. Every hallm image is pinned to the
fixed tag `:latest`, so pushing a new image does **not** change a single byte
of `k8s/myapp.yaml`. The apply is a no-op, no new ReplicaSet is created, and
the old pods keep serving the old image — while the command happily prints
`[OK] myapp deployed`.

That is a silent failure: it looks like a successful deploy and ships nothing.
`rollout restart` is what forces new pods, which then pull the current
`:latest` from the registry.

Two consequences worth knowing:

- The restart targets Deployments labelled `app=myapp` — the same label
  `hallm container remove` sweeps by. A manifest whose Deployment lacks that
  label applies fine but is never restarted.
- If you push an image by hand (`hallm container publish myapp`) and then
  re-apply, add `--restart` explicitly. Publishing alone never touches the
  cluster.

## Verify

```bash
kubectl get pods -l app=myapp                # Pod ready
kubectl get ingress myapp                    # Ingress has an address
curl -sk https://myapp.hallm.local/health    # Reachable through Traefik
```

If you used `shared-volumes`:

```bash
ls ~/.hallm/shared-volumes/myapp/            # subPath created on first mount
```

## Remove

```bash
hallm container remove myapp
```

Deletes everything in `k8s/myapp.yaml` plus PVCs / Secrets / ConfigMaps /
Ingresses labelled `app: myapp` in the namespace. Files written to
`~/.hallm/shared-volumes/myapp/` are **not** removed — `rm -rf` manually if
you want a clean slate.

## Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Pod `ImagePullBackOff` for `unregistry.hallm.local/...` | Image not built or registry trust missing. | `hallm container publish myapp`; if still failing, re-run `hallm cluster setup` so the registry CA is trusted again. |
| Ingress shows no address | TLS secret not issued yet by cert-manager. | Wait ~30s; check `kubectl describe ingress myapp` and `kubectl get certificate`. |
| `https://myapp.hallm.local` resolves but Browser warns | Cerberus CA not in your OS/browser trust store. | Import `~/.hallm/cerberus-ca.pem` (produced by `hallm secrets get-certificate`). |
| `PVC pending` for your own `*-data` PVC | Typo in `storageClassName`, or a `hallm-static` PVC with no matching PV. | Check the class spelling; for `hallm-static`, confirm the PV half exists and its `claimRef` names this PVC. |
| Deploy reported `[OK]` but the pods still run the old image | `kubectl apply` was a no-op — the `:latest` tag makes the manifest byte-identical. | Re-run with `--restart` (a build implies one automatically). See "Why the rollout restart is not optional". |
| Data gone after `hallm cluster nuke` + `setup` | The PVC used `local-path`, whose per-UUID directory is orphaned on recreate. | Move to a `hallm-static` PV+PVC pair; the old directory is still under `/var/lib/rancher/k3s/storage/`. |
| Files written through `shared-volumes` invisible on host | Forgot `subPath`, or container UID doesn't match host user. | Add `subPath: myapp`. For UID mismatches, set `securityContext.fsGroup: 1000` on the Pod. |
| `hallm container remove myapp` left a PVC behind | PVC missing `app: myapp` label. | Add the label, or `kubectl delete pvc <name>` manually. |

## Reference: real examples in the repo

- [k8s/valkey.yaml](../k8s/valkey.yaml) — minimal stateful service (PVC + Deployment + Service + TCP IngressRoute).
- [k8s/jupyter.yaml](../k8s/jupyter.yaml) — custom image + secrets + HTTPS Ingress.
- [k8s/rustfs.yaml](../k8s/rustfs.yaml) — two Ingresses (API + console) on the same Deployment.
- [k8s/shared-volumes.yaml](../k8s/shared-volumes.yaml) — the `shared-volumes` PV/PVC themselves.
