"""Local Caddy + dnsmasq network setup for hallm.local services.

Pushes ``network/Caddyfile`` to ``/etc/caddy/Caddyfile`` and ``network/dnsmasq.d``
to ``/etc/dnsmasq.d/hallm.conf``, installs a system systemd unit that runs
Caddy as the reverse proxy on ``127.0.0.2:80`` (kept off ``127.0.0.1`` so it
doesn't fight the k3d cluster's Traefik), and reloads both services.
"""

import shutil
import socket
import tempfile
from pathlib import Path

import typer

from hallm.cli.base.shell import check as _check
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.cli.base.template import render as _render
from hallm.core.settings import settings

app = typer.Typer(help="Local Caddy + dnsmasq network setup.", no_args_is_help=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Repo-relative paths are resolved lazily so importing this module doesn't
# require a discoverable hallm checkout (e.g. for `hallm mcp serve`).
def _repo_caddyfile() -> Path:
    return settings.network_path / "Caddyfile"


def _repo_dnsmasq() -> Path:
    return settings.network_path / "dnsmasq.d"


def _repo_unit_tpl() -> Path:
    return settings.network_path / "hallm-caddy.service.tpl"


_SYSTEM_CADDYFILE = Path("/etc/caddy/Caddyfile")
_SYSTEM_DNSMASQ = Path("/etc/dnsmasq.d/hallm.conf")
_SYSTEM_UNIT = Path("/etc/systemd/system/hallm-caddy.service")

_CADDY_SERVICE = "hallm-caddy.service"
_DNSMASQ_SERVICE = "dnsmasq.service"

_LOCAL_RESOLVER = "127.0.0.1"
_LOCAL_DOMAIN = "hallm.local"
# Connection types nmcli reports for managed Ethernet/Wi-Fi interfaces; we skip
# bridge/docker0/tun shims because they don't drive /etc/resolv.conf.
_NM_DNS_CONNECTION_TYPES = ("802-3-ethernet", "802-11-wireless")

_OPENCLAW_HOST = "openclaw.hallm.local"
_CADDY_BIND = "127.0.0.2"
_CADDY_PORT = 80
_OPENCLAW_BACKEND_HOST = "127.0.0.1"
_OPENCLAW_BACKEND_PORT = 18789


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_caddy_bin() -> str:
    caddy = shutil.which("caddy")
    if not caddy:
        _fail("'caddy' not found on PATH — install Caddy first (e.g. brew install caddy).")
    return caddy


def _render_unit(caddy_bin: str) -> str:
    return _render(_repo_unit_tpl().read_text(), {"CADDY_BIN": caddy_bin})


def _resolve_a(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _service_active(unit: str) -> bool:
    return _run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def _nm_active_connections() -> list[tuple[str, str, str]]:
    """Return [(name, device, type), ...] for active NM connections, or [] if NM absent."""
    result = _run(["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "c", "show", "--active"])
    if result.returncode != 0:
        return []
    conns: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            conns.append((parts[0], parts[1], parts[2]))
    return conns


def _ensure_nm_dns(resolver: str = _LOCAL_RESOLVER) -> None:
    """Make NetworkManager put `resolver` first in /etc/resolv.conf — best-effort.

    Walks the active NM connections (Ethernet/Wi-Fi only), prepends `resolver`
    to ipv4.dns, sets ipv4.ignore-auto-dns=yes so DHCP doesn't shove the
    gateway back in front, then calls `nmcli device reapply` so the change
    lands without dropping the link.
    """
    if shutil.which("nmcli") is None:
        typer.echo(
            "[warn] nmcli not on PATH — add '127.0.0.1' as the first nameserver in "
            "/etc/resolv.conf manually so the host resolves *.hallm.local via dnsmasq."
        )
        return

    targets = [
        (name, device)
        for name, device, ctype in _nm_active_connections()
        if ctype in _NM_DNS_CONNECTION_TYPES
    ]
    if not targets:
        typer.echo(
            "[warn] No active Ethernet/Wi-Fi NetworkManager connection found — "
            "configure your resolver to query 127.0.0.1 first by hand."
        )
        return

    for name, device in targets:
        typer.echo(f"==> Pointing NetworkManager connection '{name}' at {resolver}")
        _run_or_fail(
            [
                "sudo",
                "nmcli",
                "connection",
                "modify",
                name,
                "ipv4.dns",
                resolver,
                "ipv4.ignore-auto-dns",
                "yes",
                "+ipv4.dns-search",
                "",
            ],
            f"Failed to set ipv4.dns on NM connection '{name}'",
        )
        # reapply re-renders /etc/resolv.conf without a link flap; if reapply
        # bails (rare — usually stale state) the change still lands on the
        # next reconnect, so we just warn instead of failing the whole apply.
        rc = _run(["sudo", "nmcli", "device", "reapply", device]).returncode
        if rc != 0:
            typer.echo(
                f"[warn] 'nmcli device reapply {device}' failed; "
                f"bring the connection down/up manually for DNS to take effect."
            )


def _file_matches(system_path: Path, repo_path: Path) -> bool:
    try:
        return system_path.read_text() == repo_path.read_text()
    except OSError:
        return False


def _dnsmasq_conf_dir_set() -> bool:
    """True when /etc/dnsmasq.conf includes /etc/dnsmasq.d (otherwise our drop-in is ignored)."""
    try:
        for line in Path("/etc/dnsmasq.conf").read_text().splitlines():
            if line.startswith("conf-dir=/etc/dnsmasq.d"):
                return True
    except OSError:
        return False
    return False


def _resolver_first_in_resolv_conf(resolver: str) -> bool:
    """True when `resolver` is the first uncommented nameserver in /etc/resolv.conf."""
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or not line.startswith("nameserver"):
                continue
            parts = line.split()
            return len(parts) >= 2 and parts[1] == resolver
    except OSError:
        return False
    return False


def _dig_at(host: str, server: str) -> str | None:
    """Query `server` directly for an A record on `host`; return the answer or None."""
    if shutil.which("dig") is None:
        return None
    result = _run(["dig", f"@{server}", "+short", "+time=2", "+tries=1", host])
    if result.returncode != 0:
        return None
    answer = result.stdout.strip().splitlines()
    return answer[0] if answer else None


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


@app.command()
def apply() -> None:
    """Install Caddy + dnsmasq configs into /etc and (re)load both services.

    Uses sudo for /etc writes and systemctl reloads.
    """
    caddyfile = _repo_caddyfile()
    dnsmasq = _repo_dnsmasq()
    unit_tpl = _repo_unit_tpl()
    for path in (caddyfile, dnsmasq, unit_tpl):
        if not path.is_file():
            _fail(f"Missing repo file: {path}")

    caddy_bin = _resolve_caddy_bin()

    typer.echo("==> Validating Caddyfile...")
    _run_or_fail(
        [caddy_bin, "validate", "--config", str(caddyfile), "--adapter", "caddyfile"],
        "Caddyfile failed validation",
    )

    typer.echo(f"\n==> Installing {_SYSTEM_CADDYFILE}...")
    _run_or_fail(
        ["sudo", "install", "-Dm", "0644", str(caddyfile), str(_SYSTEM_CADDYFILE)],
        f"Failed to install {_SYSTEM_CADDYFILE}",
    )

    typer.echo(f"\n==> Installing {_SYSTEM_DNSMASQ}...")
    _run_or_fail(
        ["sudo", "install", "-Dm", "0644", str(dnsmasq), str(_SYSTEM_DNSMASQ)],
        f"Failed to install {_SYSTEM_DNSMASQ}",
    )
    # The Arch dnsmasq package ships an empty /etc/dnsmasq.conf with no
    # conf-dir directive, so /etc/dnsmasq.d/ is silently ignored. Ensure the
    # include is present (idempotent).
    _run_or_fail(
        [
            "sudo",
            "sh",
            "-c",
            "grep -q '^conf-dir=/etc/dnsmasq.d' /etc/dnsmasq.conf "
            "|| echo 'conf-dir=/etc/dnsmasq.d/,*.conf' >> /etc/dnsmasq.conf",
        ],
        "Failed to ensure conf-dir in /etc/dnsmasq.conf",
    )

    typer.echo(f"\n==> Installing {_SYSTEM_UNIT}...")
    rendered_unit = _render_unit(caddy_bin)
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="hallm-caddy-", suffix=".service", delete=False
    ) as tmp:
        tmp.write(rendered_unit)
        tmp_path = tmp.name
    try:
        _run_or_fail(
            ["sudo", "install", "-Dm", "0644", tmp_path, str(_SYSTEM_UNIT)],
            f"Failed to install {_SYSTEM_UNIT}",
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    typer.echo("\n==> Reloading systemd and (re)starting services...")
    _run_or_fail(["sudo", "systemctl", "daemon-reload"], "systemctl daemon-reload failed")
    _run_or_fail(
        ["sudo", "systemctl", "enable", "--now", _CADDY_SERVICE],
        f"Failed to enable {_CADDY_SERVICE}",
    )
    _run_or_fail(
        ["sudo", "systemctl", "reload-or-restart", _CADDY_SERVICE],
        f"Failed to reload {_CADDY_SERVICE}",
    )
    _run_or_fail(
        ["sudo", "systemctl", "restart", _DNSMASQ_SERVICE],
        f"Failed to restart {_DNSMASQ_SERVICE}",
    )

    typer.echo("\n==> Pointing NetworkManager DNS at the local dnsmasq...")
    _ensure_nm_dns()

    typer.echo("\nNetwork configuration applied.")


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


@app.command()
def health() -> None:
    """Validate that Caddy + dnsmasq are wired up correctly end-to-end."""
    all_ok = True

    typer.echo("==> Binaries")
    all_ok &= _check("caddy installed", shutil.which("caddy") is not None)
    all_ok &= _check("dnsmasq installed", shutil.which("dnsmasq") is not None)

    typer.echo("\n==> Installed configs match repo")
    all_ok &= _check(
        f"{_SYSTEM_CADDYFILE} matches network/Caddyfile",
        _file_matches(_SYSTEM_CADDYFILE, _repo_caddyfile()),
    )
    all_ok &= _check(
        f"{_SYSTEM_DNSMASQ} matches network/dnsmasq.d",
        _file_matches(_SYSTEM_DNSMASQ, _repo_dnsmasq()),
    )

    typer.echo("\n==> Wiring")
    all_ok &= _check(
        "/etc/dnsmasq.conf includes /etc/dnsmasq.d/*.conf",
        _dnsmasq_conf_dir_set(),
    )
    all_ok &= _check(
        f"{_LOCAL_RESOLVER} is first in /etc/resolv.conf",
        _resolver_first_in_resolv_conf(_LOCAL_RESOLVER),
    )

    typer.echo("\n==> Services")
    all_ok &= _check(f"{_CADDY_SERVICE} active", _service_active(_CADDY_SERVICE))
    all_ok &= _check(f"{_DNSMASQ_SERVICE} active", _service_active(_DNSMASQ_SERVICE))

    typer.echo("\n==> DNS")
    all_ok &= _check(
        f"{_OPENCLAW_HOST} resolves to {_CADDY_BIND}",
        _resolve_a(_OPENCLAW_HOST) == _CADDY_BIND,
    )
    # Probe the dnsmasq socket directly so we know the service answers even
    # when /etc/resolv.conf hasn't been pointed at it yet.
    # Probe through dnsmasq with a synthetic host so we don't depend on any
    # specific service being installed yet.
    probe_host = f"probe.{_LOCAL_DOMAIN}"
    all_ok &= _check(
        f"dnsmasq answers '{probe_host}' on {_LOCAL_RESOLVER}",
        _dig_at(probe_host, _LOCAL_RESOLVER) is not None,
    )

    typer.echo("\n==> Listening sockets")
    all_ok &= _check(
        f"OpenClaw gateway on {_OPENCLAW_BACKEND_HOST}:{_OPENCLAW_BACKEND_PORT}",
        _tcp_open(_OPENCLAW_BACKEND_HOST, _OPENCLAW_BACKEND_PORT),
    )
    all_ok &= _check(
        f"Caddy on {_CADDY_BIND}:{_CADDY_PORT}",
        _tcp_open(_CADDY_BIND, _CADDY_PORT),
    )

    typer.echo()
    if all_ok:
        typer.echo("Network is healthy.")
    else:
        typer.echo("One or more checks failed.", err=True)
        raise typer.Exit(code=1)
