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
| Reachable from | Same host always; other devices via Tailscale Split DNS for `hallm.local` → tailnet IP of the host running dnsmasq |

## Authentication model

Two kinds of credentials, **don't mix them**:

- **App token** — per-Application token. Used to **push** messages. Send
  as `?token=<token>` query param or `X-Gotify-Key: <token>` header.
  This is what every client app must hold.
- **User basic auth** (`admin:<password>`) — only for **management**:
  create/delete Applications, manage users. Default admin password is
  `admin` on a fresh deploy; rotate on first login.

## Get an app token

UI: log in at `https://gotify.hallm.local` → **Apps** → **Create Application**.
Copy the token (it's only shown once in some UI versions; you can always
refetch via API).

API:

```bash
curl -sk -u admin:<password> -X POST https://gotify.hallm.local/application \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-service","description":"what this app sends"}'
# → {"id":N,"token":"AgPSZ...","name":"my-service",...}
```

Store the token as `GOTIFY_APP_TOKEN` in the consumer's secret store
(`~/.hallm/<service>.env` for hallm-resident services, or whatever the
target project uses).

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
   the cluster with `uv run hallm k8s get-cert` (writes
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

Other devices on the tailnet (phone, laptop, CI box): configure
**Tailscale Split DNS** in the admin console — Add nameserver, custom,
IP = tailnet IP of the dnsmasq host, **Restrict to domain** = `hallm.local`.
Then any tailnet peer resolves `*.hallm.local` correctly.

Devices NOT on the tailnet have no way to resolve `*.hallm.local`. Either
join them to the tailnet or expose gotify through a different ingress
with a public DNS name.

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
| `Could not resolve host: gotify.hallm.local` | DNS not set up for this device. Same-host needs dnsmasq running (`hallm network apply`); tailnet peers need Split DNS configured. |
| `401 unauthorized` on `POST /message` | App token wrong/revoked, or you sent user basic auth instead of the token. |
| `403 forbidden` on `POST /application` | Used app token where user basic auth is required (management endpoints need admin). |
| Message succeeds (200) but phone doesn't buzz | Gotify Android app disconnected (battery saver killed VPN/websocket) or notification channel muted. Test from the web UI on the same browser before blaming the API. |
| `Connection refused` from tailnet peer | dnsmasq isn't listening on the tailnet IP. On the host: `ss -lnup \| grep :53` should show the tailnet IP. If missing, add `listen-address=<tailnet-ip>` to `network/dnsmasq.d` and `sudo systemctl restart dnsmasq` (reload/SIGHUP does NOT re-bind sockets). |

## Quick smoke test

From any tailnet-attached host with the CA trusted:

```bash
curl -sk https://gotify.hallm.local/health
curl -sk -X POST "https://gotify.hallm.local/message?token=$GOTIFY_APP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"smoke","message":"hello from '"$(hostname)"'","priority":5}'
```

Green health + 200 on the POST + push lands on phone = full chain works.
