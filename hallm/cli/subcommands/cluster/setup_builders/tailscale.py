"""Tailscale Kubernetes Operator install (helm).

Provides the ``tailscale`` IngressClass that backs every ``*-tailnet`` Ingress
in ``k8s/``. OAuth credentials come from ``~/.hallm/tailscale.env`` (the same
file `hallm k8s sync-secrets` would apply) — the operator expects them as
helm values at install time, so this Step reads the file directly.
"""

from typing import ClassVar

from hallm.cli.base import shell
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings

_HELM_REPO_NAME = "tailscale"
_HELM_REPO_URL = "https://pkgs.tailscale.com/helmcharts"
_CHART = "tailscale/tailscale-operator"
_RELEASE = "tailscale-operator"
_NAMESPACE = "tailscale"
_CREDS_FILE = "tailscale.env"
_REQUIRED_KEYS = ("TS_OAUTH_CLIENT_ID", "TS_OAUTH_CLIENT_SECRET")


def _load_oauth_creds() -> dict[str, str]:
    """Read OAuth client id/secret from ~/.hallm/tailscale.env."""
    path = settings.SECRETS_PATH / _CREDS_FILE
    if not path.exists():
        shell.fail(
            f"Tailscale operator install requires {path}. "
            "Create it with TS_OAUTH_CLIENT_ID and TS_OAUTH_CLIENT_SECRET "
            "(generate an OAuth client at https://login.tailscale.com/admin/settings/oauth)."
        )
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in _REQUIRED_KEYS if not values.get(k)]
    if missing:
        shell.fail(f"{path} is missing required keys: {', '.join(missing)}")
    return values


def _add_helm_repo() -> None:
    add_repo = shell.run(["helm", "repo", "add", _HELM_REPO_NAME, _HELM_REPO_URL])
    if add_repo.returncode != 0 and "already exists" not in add_repo.stderr:
        shell.fail(f"helm repo add {_HELM_REPO_NAME} failed:\n{add_repo.stderr}")
    shell.run_or_fail(["helm", "repo", "update", _HELM_REPO_NAME], "helm repo update failed")


def _install_release(creds: dict[str, str]) -> None:
    shell.run_or_fail(
        [
            "helm",
            "upgrade",
            "--install",
            _RELEASE,
            _CHART,
            "--namespace",
            _NAMESPACE,
            "--create-namespace",
            "--set-string",
            f"oauth.clientId={creds['TS_OAUTH_CLIENT_ID']}",
            "--set-string",
            f"oauth.clientSecret={creds['TS_OAUTH_CLIENT_SECRET']}",
        ],
        "helm install tailscale-operator failed",
    )


class TailscaleApp(App):
    """No manifest_path: the operator is helm-driven with secret values."""

    name: ClassVar[str] = "tailscale-operator"
    namespace: ClassVar[str] = _NAMESPACE
    wait_target: ClassVar[str | None] = "deploy/operator"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180

    def install(self) -> None:
        creds = _load_oauth_creds()
        _add_helm_repo()
        _install_release(creds)


class TailscaleStep(Step):
    name: ClassVar[str] = "Installing Tailscale operator"
    app: App = TailscaleApp()
