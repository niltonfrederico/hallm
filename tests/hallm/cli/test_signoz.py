"""Unit tests for hallm.cli.subcommands.signoz."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from hallm.cli.subcommands.signoz import _add_helm_repo
from hallm.cli.subcommands.signoz import _apply_extras
from hallm.cli.subcommands.signoz import _install_helm_release
from hallm.cli.subcommands.signoz import _wait_for_collector_ready
from hallm.cli.subcommands.signoz import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# bootstrap (top-level command)
# ---------------------------------------------------------------------------


class TestBootstrap:
    def test_happy_path(self, runner: CliRunner, k8s_dir: Path) -> None:
        (k8s_dir / "helm").mkdir()
        (k8s_dir / "helm" / "signoz-values.yaml").write_text("global: {}")
        (k8s_dir / "helm" / "k8s-infra-values.yaml").write_text("presets: {}")
        (k8s_dir / "signoz-extras.yaml").write_text("apiVersion: v1")
        (k8s_dir / "signoz-ingress.yaml").write_text("apiVersion: v1")

        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, [])

        assert result.exit_code == 0, result.output
        assert "SigNoz is wired in" in result.output
        # helm repo add + helm repo update + kubectl create ns + helm upgrade signoz +
        # kubectl wait + helm upgrade k8s-infra + 2x kubectl apply (extras + ingress)
        # = 8 subprocess calls
        assert mock.call_count == 8

    def test_helm_install_failure_exits_1(self, runner: CliRunner, k8s_dir: Path) -> None:
        (k8s_dir / "helm").mkdir()
        (k8s_dir / "helm" / "signoz-values.yaml").write_text("global: {}")

        # repo add OK, repo update OK, create ns OK, helm upgrade FAILS
        with patch(
            "subprocess.run",
            side_effect=[_cp(), _cp(), _cp(), _cp(returncode=1, stderr="boom")],
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "helm install signoz failed" in result.output

    def test_collector_wait_timeout_exits_1(self, runner: CliRunner, k8s_dir: Path) -> None:
        (k8s_dir / "helm").mkdir()
        (k8s_dir / "helm" / "signoz-values.yaml").write_text("global: {}")

        # repo add, repo update, create ns, helm upgrade, kubectl wait FAILS
        with patch(
            "subprocess.run",
            side_effect=[_cp(), _cp(), _cp(), _cp(), _cp(returncode=1, stderr="timed out")],
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "did not reach condition=Available" in result.output


# ---------------------------------------------------------------------------
# _add_helm_repo
# ---------------------------------------------------------------------------


class TestAddHelmRepo:
    def test_succeeds_on_clean_add(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            _add_helm_repo()
        assert mock.call_count == 2  # add + update

    def test_treats_already_exists_as_success(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(returncode=1, stderr="Error: repository name (signoz) already exists, ..."),
                _cp(),  # repo update
            ],
        ) as mock:
            _add_helm_repo()
        assert mock.call_count == 2

    def test_genuine_repo_add_failure_exits(self) -> None:
        with patch(
            "subprocess.run",
            return_value=_cp(returncode=1, stderr="dial tcp: lookup failed"),
        ):
            with pytest.raises(typer.Exit):
                _add_helm_repo()

    def test_repo_update_failure_exits(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(), _cp(returncode=1, stderr="net err")],
        ):
            with pytest.raises(typer.Exit):
                _add_helm_repo()


# ---------------------------------------------------------------------------
# _install_helm_release
# ---------------------------------------------------------------------------


class TestInstallHelmRelease:
    def test_invokes_helm_with_values_file(self, k8s_dir: Path) -> None:
        (k8s_dir / "helm").mkdir()
        values = k8s_dir / "helm" / "signoz-values.yaml"
        values.write_text("global: {}")

        with patch("subprocess.run", return_value=_cp()) as mock:
            _install_helm_release()

        # 1) kubectl create namespace, 2) helm upgrade --install
        assert mock.call_count == 2
        helm_cmd = mock.call_args_list[1][0][0]
        assert helm_cmd[:3] == ["helm", "upgrade", "--install"]
        assert "signoz/signoz" in helm_cmd
        assert str(values) in helm_cmd


# ---------------------------------------------------------------------------
# _wait_for_collector_ready
# ---------------------------------------------------------------------------


class TestWaitForCollector:
    def test_passes_correct_kubectl_wait_args(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            _wait_for_collector_ready()

        cmd = mock.call_args[0][0]
        assert cmd[0:2] == ["kubectl", "wait"]
        assert "deploy/signoz-otel-collector" in cmd
        assert "signoz" in cmd
        assert "--for=condition=Available" in cmd


# ---------------------------------------------------------------------------
# _apply_extras
# ---------------------------------------------------------------------------


class TestApplyExtras:
    def test_applies_both_manifests(self, k8s_dir: Path) -> None:
        (k8s_dir / "signoz-extras.yaml").write_text("kind: Deployment")
        (k8s_dir / "signoz-ingress.yaml").write_text("kind: Ingress")

        with patch("subprocess.run", return_value=_cp()) as mock:
            _apply_extras()

        assert mock.call_count == 2
        first_input = mock.call_args_list[0][1]["input"]
        second_input = mock.call_args_list[1][1]["input"]
        assert "Deployment" in first_input
        assert "Ingress" in second_input

    def test_extras_apply_failure_exits_1(self, k8s_dir: Path) -> None:
        (k8s_dir / "signoz-extras.yaml").write_text("kind: Deployment")
        (k8s_dir / "signoz-ingress.yaml").write_text("kind: Ingress")

        with patch(
            "subprocess.run",
            return_value=_cp(returncode=1, stderr="invalid yaml"),
        ):
            with pytest.raises(typer.Exit):
                _apply_extras()


# ---------------------------------------------------------------------------
# Integration safeguards
# ---------------------------------------------------------------------------


def test_signoz_skipped_from_generic_apply_loop() -> None:
    """signoz-{extras,ingress}.yaml must NOT be applied by the generic apply loop."""
    from hallm.cli.subcommands.cluster import _SETUP_SKIP_MANIFESTS

    assert "signoz-extras.yaml" in _SETUP_SKIP_MANIFESTS
    assert "signoz-ingress.yaml" in _SETUP_SKIP_MANIFESTS


def test_otel_endpoint_points_at_signoz_collector() -> None:
    """The hallm app must already point its OTLP exporter at the in-cluster collector."""
    assert "signoz-otel-collector.signoz" in settings.otel_endpoint


def test_signoz_init_sql_present_in_bootstrap_dir() -> None:
    """signoz_monitor role creation must run as part of `hallm db bootstrap`."""
    init_sql = settings.CLI_PATH / "subcommands" / "bootstrap" / "init.signoz.sql"
    assert init_sql.exists()
    body = init_sql.read_text()
    # The literal role name is injected via envsubst from the Job env (set in
    # k8s/jobs/db-bootstrap.yaml) — the SQL template references it by var name.
    assert "${SIGNOZ_MONITOR_USER}" in body
    assert "pg_monitor" in body


# ---------------------------------------------------------------------------
# Manifest structure: every scrape target maps to its own SigNoz service
# ---------------------------------------------------------------------------


_EXPECTED_SIGNOZ_SERVICES: tuple[str, ...] = (
    "postgres",
    "valkey",
    "gotify",
    "paperless",
    "glitchtip",
    "ots",
    "openclaw",
    "activitywatch",
    "rustfs",
    "ollama",
)


def test_signoz_extras_manifest_assigns_service_name_per_deployment() -> None:
    """Each scrape target must surface in SigNoz under its own service.name.

    The collector ConfigMap drives this: one resource processor per service
    (`resource/<name>`) sets `service.name=<name>` and feeds a dedicated
    pipeline (`metrics/<name>`).  Without this, every metric would land under
    a single generic service in the SigNoz UI.
    """
    manifest = (settings.K8S_PATH / "signoz-extras.yaml").read_text()
    for name in _EXPECTED_SIGNOZ_SERVICES:
        assert f"resource/{name}:" in manifest
        assert f"metrics/{name}:" in manifest
        assert f"value: {name}" in manifest


def test_signoz_values_enables_logs_and_label_based_service_name() -> None:
    """k8s-infra must collect pod logs and promote the `app` label to service.name.

    Together these make every Deployment appear as its own service in the
    SigNoz UI (logs tab + services tab) without per-pod instrumentation.

    The agent config lives in the standalone k8s-infra-values.yaml since
    signoz/signoz >= 0.55 dropped the k8s-infra subchart.
    """
    values = (settings.K8S_PATH / "helm" / "k8s-infra-values.yaml").read_text()
    assert "logsCollection:" in values
    assert "extractLabels:" in values
    assert "tag_name: service.name" in values
    assert "key: app" in values
