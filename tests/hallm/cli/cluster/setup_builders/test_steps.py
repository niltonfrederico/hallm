"""Tests for concrete and synthetic Steps in cluster.setup_builders."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces import (
    BootstrapNamespacesStep,
)
from hallm.cli.subcommands.cluster.setup_builders.cerberus_pki import CerberusPkiApp
from hallm.cli.subcommands.cluster.setup_builders.cerberus_pki import CerberusPkiStep
from hallm.cli.subcommands.cluster.setup_builders.cert_manager import CertManagerApp
from hallm.cli.subcommands.cluster.setup_builders.cert_manager import CertManagerStep
from hallm.cli.subcommands.cluster.setup_builders.create_cluster import CreateClusterStep
from hallm.cli.subcommands.cluster.setup_builders.jupyter import JupyterApp
from hallm.cli.subcommands.cluster.setup_builders.jupyter import JupyterStep
from hallm.cli.subcommands.cluster.setup_builders.memory_mcp import MemoryMcpApp
from hallm.cli.subcommands.cluster.setup_builders.memory_mcp import MemoryMcpStep
from hallm.cli.subcommands.cluster.setup_builders.mount_storage import MountStorageStep
from hallm.cli.subcommands.cluster.setup_builders.paperless import PaperlessApp
from hallm.cli.subcommands.cluster.setup_builders.paperless import PaperlessStep
from hallm.cli.subcommands.cluster.setup_builders.postgres import PostgresApp
from hallm.cli.subcommands.cluster.setup_builders.postgres import PostgresStep
from hallm.cli.subcommands.cluster.setup_builders.preflight import PreflightStep
from hallm.cli.subcommands.cluster.setup_builders.rocm_plugin import ROCmPluginApp
from hallm.cli.subcommands.cluster.setup_builders.rocm_plugin import ROCmPluginStep
from hallm.cli.subcommands.cluster.setup_builders.rustfs import RustfsApp
from hallm.cli.subcommands.cluster.setup_builders.rustfs import RustfsStep
from hallm.cli.subcommands.cluster.setup_builders.signoz import SignozApp
from hallm.cli.subcommands.cluster.setup_builders.signoz import SignozStep
from hallm.cli.subcommands.cluster.setup_builders.sync_secrets import SyncSecretsStep
from hallm.cli.subcommands.cluster.setup_builders.traefik_config import TraefikConfigApp
from hallm.cli.subcommands.cluster.setup_builders.traefik_config import TraefikConfigStep
from hallm.cli.subcommands.cluster.setup_builders.trust_docker_ca import TrustDockerCaStep
from hallm.cli.subcommands.cluster.setup_builders.unregistry import UnregistryApp
from hallm.cli.subcommands.cluster.setup_builders.unregistry import UnregistryStep
from hallm.cli.subcommands.cluster.setup_builders.valkey import ValkeyApp
from hallm.cli.subcommands.cluster.setup_builders.valkey import ValkeyStep
from hallm.cli.subcommands.cluster.setup_builders.wait_api import WaitApiStep
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# Synthetic Steps
# ---------------------------------------------------------------------------


class TestBootstrapNamespacesStep:
    def test_creates_each_namespace(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces._run",
            return_value=_cp(),
        ) as mock:
            BootstrapNamespacesStep(frozenset({"foo", "bar"})).run()
        # One kubectl create call per namespace (sorted).
        called = [c.args[0] for c in mock.call_args_list]
        assert called == [
            ["kubectl", "create", "namespace", "bar"],
            ["kubectl", "create", "namespace", "foo"],
        ]

    def test_already_exists_is_idempotent(self) -> None:
        result = _cp(
            returncode=1,
            stderr='Error from server (AlreadyExists): namespaces "foo" already exists',
        )
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces._run",
            return_value=result,
        ):
            BootstrapNamespacesStep(frozenset({"foo"})).run()  # no exception

    def test_other_failure_raises(self) -> None:
        result = _cp(returncode=1, stderr="permission denied")
        with (
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces._run",
                return_value=result,
            ),
            pytest.raises(RuntimeError, match="permission denied"),
        ):
            BootstrapNamespacesStep(frozenset({"foo"})).run()

    def test_required_namespaces_empty(self) -> None:
        assert BootstrapNamespacesStep(frozenset({"a"})).required_namespaces == frozenset()


class TestSyncSecretsStep:
    def test_delegates_to_secrets_module(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.sync_secrets._secrets._sync_secrets"
        ) as mock:
            SyncSecretsStep().run()
        mock.assert_called_once()


# ---------------------------------------------------------------------------
# Host / cluster lifecycle Steps
# ---------------------------------------------------------------------------


class TestPreflightStep:
    def test_delegates_to_run_preflight(self) -> None:
        with patch("hallm.cli.subcommands.cluster.setup_builders.preflight._run_preflight") as mock:
            PreflightStep().run()
        mock.assert_called_once()


class TestMountStorageStep:
    def test_pre_creates_secrets_dir_and_run_mounts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path / "secrets")
        step = MountStorageStep()
        step.pre()
        assert (tmp_path / "secrets").is_dir()

        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.mount_storage._mount_storage"
        ) as mock:
            step.run()
        mock.assert_called_once()


class TestCreateClusterStep:
    def test_run_calls_k3d_cluster_create(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.create_cluster._docker.run_or_fail",
            return_value=_cp(),
        ) as mock:
            CreateClusterStep().run()
        mock.assert_called_once()
        cmd = mock.call_args.args[0]
        assert cmd[:3] == ["k3d", "cluster", "create"]


class TestWaitApiStep:
    def test_marker_flag(self) -> None:
        assert WaitApiStep.is_cluster_ready_marker is True

    def test_run_polls_until_ready(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.wait_api.poll_until",
            return_value=True,
        ):
            WaitApiStep().run()  # no exception

    def test_run_fails_when_api_never_ready(self) -> None:
        import typer

        with (
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.wait_api.poll_until",
                return_value=False,
            ),
            pytest.raises(typer.Exit),
        ):
            WaitApiStep().run()


class TestTrustDockerCaStep:
    def test_delegates_to_secrets_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path)
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.trust_docker_ca._secrets._configure_docker_registry_cert"
        ) as mock:
            TrustDockerCaStep().run()
        mock.assert_called_once()


# ---------------------------------------------------------------------------
# Plugin / PKI Steps
# ---------------------------------------------------------------------------


class TestTraefikConfigApp:
    def test_step_uses_app(self) -> None:
        step = TraefikConfigStep()
        assert isinstance(step.app, TraefikConfigApp)
        assert step.app.namespace == "kube-system"
        assert step.required_namespaces == frozenset({"kube-system"})


class TestRocmPluginApp:
    def test_url_set(self) -> None:
        assert ROCmPluginApp.manifest_url is not None
        step = ROCmPluginStep()
        assert step.app is not None
        assert step.app.namespace == "kube-system"


class TestCertManagerApp:
    def test_wait_target_configured(self) -> None:
        assert CertManagerApp.wait_target == "deploy/cert-manager-webhook"
        assert CertManagerApp.namespace == "cert-manager"
        step = CertManagerStep()
        assert step.required_namespaces == frozenset({"cert-manager"})


class TestCerberusPkiStep:
    def test_restore_branch_when_keys_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path)
        (tmp_path / "cerberus-ca.pem").write_text("PEM")
        (tmp_path / "cerberus-ca.key").write_text("KEY")
        step = CerberusPkiStep()
        assert step._restore_mode is True

        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.cerberus_pki._secrets._restore_cerberus_from_files"
        ) as mock_restore:
            step.run()
        mock_restore.assert_called_once()

        # post_validate / post are no-ops in restore mode.
        step.post_validate()
        step.post()

    def test_fresh_install_branch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path)
        step = CerberusPkiStep()
        assert step._restore_mode is False

        with patch.object(CerberusPkiApp, "install") as mock_install:
            step.run()
        mock_install.assert_called_once()

        # post_validate delegates to App.wait via super().post_validate().
        with patch.object(CerberusPkiApp, "wait") as mock_wait:
            step.post_validate()
        mock_wait.assert_called_once()

        # post exports CA.
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.cerberus_pki._secrets._export_cerberus_ca"
        ) as mock_export:
            step.post()
        mock_export.assert_called_once()


# ---------------------------------------------------------------------------
# Service Steps
# ---------------------------------------------------------------------------


class TestUnregistryStep:
    def test_app_configured(self) -> None:
        step = UnregistryStep()
        assert isinstance(step.app, UnregistryApp)
        assert step.app.namespace == "kube-system"


class TestPostgresStep:
    def test_app_and_secrets_flag(self) -> None:
        step = PostgresStep()
        assert isinstance(step.app, PostgresApp)
        assert PostgresStep.needs_secrets is True
        assert step.app.wait_target == "deploy/postgres"

    def test_post_runs_db_bootstrap(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.postgres._db._run_bootstrap"
        ) as mock:
            PostgresStep().post()
        mock.assert_called_once()


class TestSimpleServiceApps:
    def test_valkey(self) -> None:
        step = ValkeyStep()
        assert isinstance(step.app, ValkeyApp)
        assert step.app.wait_target == "deploy/valkey"
        assert ValkeyStep.needs_secrets is True

    def test_rustfs(self) -> None:
        step = RustfsStep()
        assert isinstance(step.app, RustfsApp)
        assert step.app.wait_target == "deploy/rustfs"
        assert RustfsStep.needs_secrets is True

    def test_paperless(self) -> None:
        step = PaperlessStep()
        assert isinstance(step.app, PaperlessApp)
        assert step.app.wait_target == "deploy/paperless"

    def test_jupyter(self) -> None:
        step = JupyterStep()
        assert isinstance(step.app, JupyterApp)
        assert step.app.wait_target == "deploy/jupyter"
        assert JupyterStep.needs_secrets is False

    def test_memory_mcp(self) -> None:
        step = MemoryMcpStep()
        assert isinstance(step.app, MemoryMcpApp)
        assert step.app.wait_target == "deploy/memory-mcp"


class TestSignozStep:
    def test_install_delegates_to_signoz_bootstrap(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.signoz._signoz._run_bootstrap"
        ) as mock:
            SignozApp().install()
        mock.assert_called_once()

    def test_step_namespace(self) -> None:
        step = SignozStep()
        assert step.required_namespaces == frozenset({"signoz"})
