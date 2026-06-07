"""Headlamp plugin lifecycle.

Builds the in-repo ``plugins/hallm-links`` Headlamp plugin, packs the
resulting ``dist/`` into a ConfigMap, and restarts the headlamp Deployment
so the new bundle is loaded.

The plugin source lives at ``$REPO/plugins/hallm-links``.  Headlamp loads
plugins from ``-plugins-dir=/headlamp-plugins`` and expects each plugin
to be a folder containing ``main.js`` + ``package.json``.  We mount the
ConfigMap at ``/headlamp-plugins/hallm-links`` to satisfy that layout.
"""

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings

app = typer.Typer(help="Headlamp plugin operations.", no_args_is_help=True)

_CONFIGMAP = "headlamp-plugin-hallm-links"
_NAMESPACE = "kube-system"
_PLUGIN_DIR_NAME = "hallm-links"


def _plugin_root():
    return settings.repo_root / "plugins" / _PLUGIN_DIR_NAME


def _build_plugin() -> None:
    plugin_root = _plugin_root()
    if not plugin_root.exists():
        _fail(f"Plugin source not found at {plugin_root}")

    typer.echo(f"==> npm install in {plugin_root}")
    _run_or_fail(
        ["npm", "install", "--prefix", str(plugin_root)],
        "npm install failed",
    )

    typer.echo("==> npm run build")
    _run_or_fail(
        ["npm", "run", "build", "--prefix", str(plugin_root)],
        "npm run build failed",
    )


def _pack_configmap() -> None:
    plugin_root = _plugin_root()
    dist = plugin_root / "dist"
    main_js = dist / "main.js"
    pkg_json = plugin_root / "package.json"

    if not main_js.exists():
        _fail(f"Build output missing: {main_js}")

    typer.echo(f"==> Replacing ConfigMap {_NAMESPACE}/{_CONFIGMAP}")
    _run(["kubectl", "-n", _NAMESPACE, "delete", "configmap", _CONFIGMAP])
    _run_or_fail(
        [
            "kubectl",
            "-n",
            _NAMESPACE,
            "create",
            "configmap",
            _CONFIGMAP,
            f"--from-file=main.js={main_js}",
            f"--from-file=package.json={pkg_json}",
        ],
        "kubectl create configmap failed",
    )


def _restart_headlamp() -> None:
    typer.echo("==> Rolling out headlamp Deployment")
    _run_or_fail(
        ["kubectl", "-n", _NAMESPACE, "rollout", "restart", "deployment/headlamp"],
        "rollout restart failed",
    )
    kubectl.wait(
        "deploy/headlamp",
        "Available",
        namespace=_NAMESPACE,
        timeout="120s",
    )


@app.command()
def sync() -> None:
    """Build the hallm-links plugin and reload Headlamp.

    Runs ``npm install`` + ``npm run build`` in ``plugins/hallm-links``,
    packs ``dist/main.js`` + ``package.json`` into the
    ``headlamp-plugin-hallm-links`` ConfigMap, and rolls the headlamp
    Deployment so the new bundle is picked up.
    """
    _build_plugin()
    _pack_configmap()
    _restart_headlamp()
    typer.echo("\nHeadlamp plugin synced. Visit https://headlamp.hallm.local")
