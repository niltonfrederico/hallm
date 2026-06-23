# hallm cluster — resource stats snapshot (2026-06-18)

Captured immediately before a planned `k3d cluster stop hallm` (for offline tests). Single-node k3d cluster `hallm`.

## Provenance & caveats

| Metric | Source | Nature |
| --- | --- | --- |
| Requested / Limits | pod specs (`kubectl get pods -o json`) | exact, configured |
| Current CPU / Mem | metrics-server (`kubectl top`) | instantaneous snapshot |
| **Mem peak** | cgroup v2 `memory.peak` | high-water mark since pod start |
| Mem (cgroup now) | cgroup v2 `memory.current` | instantaneous, cross-check |

> No time-series store (Prometheus/SigNoz) is active, so historical **min** and **CPU peak** over time are not retained. `memory.peak` is the only true historical high-water mark available; CPU is cumulative (no gauge peak), so only the current snapshot is shown. 'Min' RAM is not recoverable retroactively — the current snapshot is the closest point sample.

## Node — k3d-hallm-server-0

| | CPU | Memory |
| --- | --- | --- |
| Capacity | 8 cores | 15.54 Gi |
| Allocatable | 8 cores | 15.54 Gi |
| Current usage | 0.07 cores | 2.90 Gi |
| Σ Requests | 1.4 cores | 2.20 Gi |
| Σ Limits | 10 cores | 9.42 Gi |
| Σ Mem peak (all pods) | — | 3.27 Gi |

## Per-pod

| Namespace | Pod | QoS | CPU req | CPU lim | CPU now | Mem req | Mem lim | Mem now | **Mem peak** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cert-manager | cert-manager-59bb5f579d-2l2lt | BestEffort | — | — | 0.001 | — | — | 87 Mi | **110 Mi** |
| cert-manager | cert-manager-cainjector-7c4895dc49-bvxzk | BestEffort | — | — | 0.001 | — | — | 62 Mi | **77 Mi** |
| cert-manager | cert-manager-webhook-c8cd4d48d-pgz26 | BestEffort | — | — | 0.001 | — | — | 60 Mi | **77 Mi** |
| default | gitea-d6f8db65f-rkdk2 | Burstable | 0.05 | 1 | 0.001 | 256 Mi | 1.00 Gi | 195 Mi | **1.00 Gi** |
| default | gotify-bd49996c7-nxbjr | Burstable | 0.1 | 0.5 | 0.001 | 64 Mi | 256 Mi | 36 Mi | **54 Mi** |
| default | ladder-67fd5655dc-gjscp | Burstable | 0.05 | 0.5 | 0.001 | 64 Mi | 256 Mi | 14 Mi | **21 Mi** |
| default | leantime-7dcfbb9965-2rdzt | Burstable | 0.1 | 1 | 0.011 | 256 Mi | 1.00 Gi | 177 Mi | **277 Mi** |
| default | postgres-67f5fdc84c-x27fm | Burstable | 0.25 | 1 | 0.004 | 256 Mi | 1.00 Gi | 63 Mi | **112 Mi** |
| default | rustfs-5b744d877c-rnfbj | Burstable | 0.2 | 2 | 0.001 | 256 Mi | 2.00 Gi | 51 Mi | **181 Mi** |
| default | sure-5744b6d6cb-8b4h4 | Burstable | 0.2 | 2 | 0.001 | 512 Mi | 2.00 Gi | 312 Mi | **370 Mi** |
| default | sure-worker-69dcdd7d9d-swls7 | Burstable | 0.1 | 1 | 0.001 | 256 Mi | 1.00 Gi | 341 Mi | **389 Mi** |
| default | valkey-6b9474c5d7-cdbq8 | Burstable | 0.1 | 0.5 | 0.003 | 128 Mi | 512 Mi | 13 Mi | **55 Mi** |
| kube-system | amdgpu-device-plugin-daemonset-5v2zb | BestEffort | — | — | 0 | — | — | 10 Mi | **25 Mi** |
| kube-system | coredns-ccb96694c-plptj | Burstable | 0.1 | — | 0.001 | 70 Mi | 170 Mi | 73 Mi | **87 Mi** |
| kube-system | headlamp-7cd845f5dd-m9w62 | Burstable | 0.05 | 0.5 | 0.001 | 64 Mi | 256 Mi | 53 Mi | **83 Mi** |
| kube-system | local-path-provisioner-5cf85fd84d-8682c | BestEffort | — | — | 0.001 | — | — | 37 Mi | **52 Mi** |
| kube-system | metrics-server-5985cbc9d7-hzsss | Burstable | 0.1 | — | 0.002 | 70 Mi | — | 75 Mi | **85 Mi** |
| kube-system | svclb-traefik-139ba337-zfrdn | BestEffort | — | — | 0 | — | — | 1 Mi | **8 Mi** |
| kube-system | traefik-868fcc588f-cj2kb | BestEffort | — | — | 0.001 | — | — | 146 Mi | **221 Mi** |
| kube-system | unregistry-rl4tq | BestEffort | — | — | 0 | — | — | 22 Mi | **37 Mi** |

_Totals: 20 pods · Σ requests 1.4 CPU / 2.20 Gi · Σ limits 10 CPU / 9.42 Gi · Σ mem peak 3.27 Gi._
