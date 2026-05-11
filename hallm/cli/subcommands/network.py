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


def _file_matches(system_path: Path, repo_path: Path) -> bool:
    try:
        return system_path.read_text() == repo_path.read_text()
    except OSError:
        return False


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
        ["sudo", "systemctl", "reload", _DNSMASQ_SERVICE],
        f"Failed to reload {_DNSMASQ_SERVICE}",
    )

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

    typer.echo("\n==> Services")
    all_ok &= _check(f"{_CADDY_SERVICE} active", _service_active(_CADDY_SERVICE))
    all_ok &= _check(f"{_DNSMASQ_SERVICE} active", _service_active(_DNSMASQ_SERVICE))

    typer.echo("\n==> DNS")
    all_ok &= _check(
        f"{_OPENCLAW_HOST} resolves to {_CADDY_BIND}",
        _resolve_a(_OPENCLAW_HOST) == _CADDY_BIND,
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
