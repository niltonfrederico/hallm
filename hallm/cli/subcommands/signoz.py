"""SigNoz observability bootstrap.

Installs two Helm releases — the SigNoz core (frontend + ClickHouse + main
OTEL collector) and the standalone k8s-infra agents (cluster receiver +
node DaemonSet for hostmetrics, kubeletstats, and pod log collection) —
then applies the auxiliary OTEL collector that scrapes Postgres, Valkey,
and HTTP liveness for the rest of the hallm stack.  Driven by
``hallm signoz bootstrap``; also called from ``hallm cluster setup``.

The k8s-infra chart is a separate release because signoz/signoz >= 0.55
no longer bundles it as a subchart.
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
_K8S_INFRA_RELEASE = "k8s-infra"


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


def _install_k8s_infra_release() -> None:
    """Install / upgrade the standalone k8s-infra chart.

    Deploys the cluster receiver + node DaemonSet that feed the SigNoz
    Infrastructure tab and tail /var/log/pods into the Logs tab.
    """
    values_file = settings.K8S_PATH / "helm" / "k8s-infra-values.yaml"
    _run_or_fail(
        [
            "helm",
            "upgrade",
            "--install",
            _K8S_INFRA_RELEASE,
            "signoz/k8s-infra",
            "-n",
            _SIGNOZ_NAMESPACE,
            "-f",
            str(values_file),
        ],
        "helm install k8s-infra failed",
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

    typer.echo("\n==> Installing k8s-infra agents (cluster receiver + node DaemonSet)...")
    _install_k8s_infra_release()

    typer.echo("\n==> Applying auxiliary collector + Ingress...")
    _apply_extras()

    typer.echo("\nSigNoz is wired in. Visit https://signoz.hallm.local once the frontend is ready.")


@app.command()
def bootstrap() -> None:
    """Install SigNoz and make it aware of the cluster, deployments, databases, and services.

    Runs helm upgrade --install for the SigNoz core chart and the
    standalone k8s-infra chart (cluster/node/pod metrics + pod log
    collection), waits for the main OTEL collector to be ready, then
    applies the auxiliary collector that scrapes Postgres / Valkey /
    HTTP endpoints.
    """
    _run_bootstrap()
