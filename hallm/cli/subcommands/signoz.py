"""SigNoz observability bootstrap.

Installs the SigNoz Helm release (frontend + ClickHouse + main OTEL collector
+ k8s-infra cluster/agent receivers) and applies the auxiliary OTEL collector
that scrapes Postgres, Valkey, and HTTP liveness for the rest of the hallm
stack.  Driven by ``hallm signoz bootstrap``; also called from
``hallm cluster setup``.
"""

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings

app = typer.Typer(help="SigNoz observability operations.", no_args_is_help=True)

_SIGNOZ_HELM_REPO = "https://charts.signoz.io"
_SIGNOZ_NAMESPACE = "signoz"
_DEFAULT_NAMESPACE = "default"


def _manifest(name: str) -> str:
    return (settings.K8S_PATH / name).read_text()


def _add_helm_repo() -> None:
    add_repo = _run(["helm", "repo", "add", "signoz", _SIGNOZ_HELM_REPO])
    if add_repo.returncode != 0 and "already exists" not in add_repo.stderr:
        _fail(f"helm repo add signoz failed:\n{add_repo.stderr}")
    _run_or_fail(["helm", "repo", "update"], "helm repo update failed")


def _install_helm_release() -> None:
    """Install / upgrade the SigNoz Helm release with hallm's values."""
    _run(["kubectl", "create", "namespace", _SIGNOZ_NAMESPACE])  # idempotent

    values_file = settings.K8S_PATH / "helm" / "signoz-values.yaml"
    _run_or_fail(
        [
            "helm",
            "upgrade",
            "--install",
            "signoz",
            "signoz/signoz",
            "-n",
            _SIGNOZ_NAMESPACE,
            "-f",
            str(values_file),
        ],
        "helm install signoz failed",
    )


def _wait_for_collector_ready() -> None:
    """Block until the main signoz-otel-collector Deployment is Available.

    The auxiliary collector ships data over OTLP to this endpoint; without it
    healthy the extras pod logs nothing but connection refused.
    """
    kubectl.wait(
        "deploy/signoz-otel-collector",
        "Available",
        namespace=_SIGNOZ_NAMESPACE,
        timeout="420s",
    )


def _apply_extras() -> None:
    """Apply the auxiliary collector + Ingress for the SigNoz frontend."""
    kubectl.apply(_manifest("signoz-extras.yaml"), label="SigNoz extras collector")
    kubectl.apply(_manifest("signoz-ingress.yaml"), label="SigNoz Ingress")


def _run_bootstrap() -> None:
    """End-to-end bootstrap: helm release, wait for collector, apply extras."""
    typer.echo("==> Adding SigNoz helm repo...")
    _add_helm_repo()

    typer.echo("\n==> Installing SigNoz helm release...")
    _install_helm_release()

    typer.echo("\n==> Waiting for signoz-otel-collector to become Available...")
    _wait_for_collector_ready()

    typer.echo("\n==> Applying auxiliary collector + Ingress...")
    _apply_extras()

    typer.echo("\nSigNoz is wired in. Visit https://signoz.hallm.local once the frontend is ready.")


@app.command()
def bootstrap() -> None:
    """Install SigNoz and make it aware of the cluster, deployments, databases, and services.

    Runs helm upgrade --install for the SigNoz chart (which bundles the
    k8s-infra subchart for cluster/node/pod metrics), waits for the main
    OTEL collector to be ready, then applies the auxiliary collector that
    scrapes Postgres / Valkey / HTTP endpoints.
    """
    _run_bootstrap()
