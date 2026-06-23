# Sending notifications to gotify (hallm cluster)

Portable reference for any app that wants to push to the gotify instance
running in the hallm k3d cluster. Copy this file into the consuming
project's `docs/` (or `.claude/`) so the assistant has the contract.

## Where gotify lives

| Concern | Value |
| --- | --- |
| Public URL | `https://gotify.hallm.local` |
| Health probe | `GET /health` → `{"health":"green","database":"green"}` |
| Hosted by | Traefik Ingress in the `hallm` k3d cluster (namespace `default`) |
| TLS | Self-signed by the **Cerberus CA** (cluster-issuer `cerberus-ca`) |
| Reachable from | Same host that runs `dnsmasq` (local only). Other devices need their own resolver for `*.hallm.local` (e.g. /etc/hosts pointing at the host running Traefik). |

## Authentication

Push uses a per-Application token. Send it as the `?token=<token>` query
param or the `X-Gotify-Key: <token>` header — either works, the header
is preferred so the secret doesn't end up in URL logs.

Applications are pre-provisioned out of band. Ask the cluster operator
for the token for your service and store it as `GOTIFY_APP_TOKEN` in the
consumer's secret store (`~/.hallm/<service>.env` for hallm-resident
services, or whatever the target project uses).

## Send a message

Minimum payload — `title`, `message`. Optional — `priority` (int, 0–10;
gotify maps to Android notification importance: ≥4 alerts with sound,
≥8 high-priority).

```bash
curl -sk -X POST "https://gotify.hallm.local/message?token=$GOTIFY_APP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "deploy finished",
    "message": "my-service v1.2.3 is live",
    "priority": 5
  }'
# → {"id":1,"appid":N,"message":"...","title":"...","priority":5,"date":"..."}
```

Header-style auth (equivalent, preferred when the token shouldn't appear
in URLs/logs):

```bash
curl -sk -X POST https://gotify.hallm.local/message \
  -H "X-Gotify-Key: $GOTIFY_APP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"...","message":"..."}'
```

### Markdown / extras

Gotify supports markdown in `message` if you set the `extras` envelope:

```json
{
  "title": "alert",
  "message": "**bold** and `code` and [links](https://example.com)",
  "priority": 5,
  "extras": {
    "client::display": {"contentType": "text/markdown"}
  }
}
```

## TLS — Cerberus CA

The cert is signed by the local self-signed Cerberus CA. Three options:

1. **Verify properly** (recommended for long-lived services): bundle the
   Cerberus CA cert into the consumer. Fetch it on the host that owns
   the cluster with `uv run hallm secrets get-certificate` (writes
   `~/.hallm/cerberus-ca.crt`). Then point your HTTP client at it
   (Python: `verify="/path/to/cerberus-ca.crt"`; Node:
   `NODE_EXTRA_CA_CERTS=/path/to/cerberus-ca.crt`).
2. **Trust at the OS level**: copy the CA into the system trust store
   (`/usr/local/share/ca-certificates/` + `update-ca-certificates` on
   Debian-likes; `/etc/ca-certificates/trust-source/anchors/` +
   `trust extract-compat` on Arch).
3. **Skip verification** (`-k` / `verify=False`) — only for one-off
   smoke tests, never for production code.

## DNS — outside the host

Same machine: `dnsmasq` (managed by `hallm network apply`) resolves
`*.hallm.local` automatically.

Other devices: no automatic resolution today. Options: add an
`/etc/hosts` entry pointing `gotify.hallm.local` at the cluster host's
LAN IP, or expose gotify through a different ingress with a public DNS
name. (A Tailscale Split DNS setup used to handle this; it was removed
when the tailnet was retired.)

## Python — use the hallm client if you're in this monorepo

If your service is inside the `hallm` repo, prefer the bundled async
client over hand-rolled `httpx`:

```python
from hallm.core.gotify import GotifyClient

async with GotifyClient() as g:           # reads GOTIFY_URL + GOTIFY_APP_TOKEN
    await g.push(title="deploy finished", message="v1.2.3 live", priority=5)
```

Env contract:

| Var | Default | Used for |
| --- | --- | --- |
| `GOTIFY_URL` | `https://gotify.hallm.local` | Base URL |
| `GOTIFY_APP_TOKEN` | `""` | Per-app push token |
| `GOTIFY_ENABLED` | `true` | Feature flag (lib doesn't enforce; caller checks) |

## Python — standalone (other repos)

No hallm dependency. Plain `httpx`:

```python
import httpx

async def notify(title: str, message: str, *, priority: int = 5) -> None:
    async with httpx.AsyncClient(
        base_url="https://gotify.hallm.local",
        verify="/path/to/cerberus-ca.crt",   # or False for dev
        timeout=10.0,
    ) as client:
        r = await client.post(
            "/message",
            headers={"X-Gotify-Key": os.environ["GOTIFY_APP_TOKEN"]},
            json={"title": title, "message": message, "priority": priority},
        )
        r.raise_for_status()
```

## Failure modes worth knowing

| Symptom | Cause |
| --- | --- |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Cerberus CA not trusted by the client. See **TLS** section. |
| `Could not resolve host: gotify.hallm.local` | DNS not set up for this device. Same-host needs dnsmasq running (`hallm network apply`); other hosts need an `/etc/hosts` entry or another resolver pointing at the cluster host. |
| `401 unauthorized` on `POST /message` | App token missing, wrong, or revoked. Confirm `GOTIFY_APP_TOKEN` matches the Application you were given. |
| Message succeeds (200) but phone doesn't buzz | Gotify Android app disconnected (battery saver killed VPN/websocket) or notification channel muted. Test from the web UI on the same browser before blaming the API. |
| `Connection refused` from another host | dnsmasq is listening on the host's loopback only; remote hosts can't reach it. Either add an `/etc/hosts` entry on the remote host or bind dnsmasq on a LAN-reachable address via `listen-address=` in `network/dnsmasq.d`, then `sudo systemctl restart dnsmasq`. |

## Quick smoke test

From any host that can resolve `gotify.hallm.local` and trusts the Cerberus CA:

```bash
curl -sk https://gotify.hallm.local/health
curl -sk -X POST "https://gotify.hallm.local/message?token=$GOTIFY_APP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"smoke","message":"hello from '"$(hostname)"'","priority":5}'
```

Green health + 200 on the POST + push lands on phone = full chain works.
