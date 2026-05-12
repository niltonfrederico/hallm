"""Tests for concrete and synthetic Steps in cluster.setup_builders."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hallm.cli.subcommands.cluster.setup_builders.base import SetupStepError
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
from hallm.cli.subcommands.cluster.setup_builders.shared_volumes import SharedVolumesApp
from hallm.cli.subcommands.cluster.setup_builders.shared_volumes import SharedVolumesStep
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
        monkeypatch.setattr(settings, "SHARED_VOLUMES_PATH", tmp_path / "shared-volumes")
        step = MountStorageStep()
        step.pre()
        assert (tmp_path / "secrets").is_dir()
        assert (tmp_path / "shared-volumes").is_dir()

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
        assert any(
            arg.endswith(f":{settings.SHARED_VOLUMES_NODE_PATH}@all")
            and str(settings.SHARED_VOLUMES_PATH) in arg
            for arg in cmd
        )

    def test_is_satisfied_true_when_cluster_listed(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.create_cluster._docker.run",
            return_value=_cp(stdout="hallm  1/1  1/1\n"),
        ) as mock:
            assert CreateClusterStep().is_satisfied() is True
        cmd = mock.call_args.args[0]
        assert cmd[:3] == ["k3d", "cluster", "list"]

    def test_is_satisfied_false_on_nonzero_exit(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.create_cluster._docker.run",
            return_value=_cp(returncode=1, stdout=""),
        ):
            assert CreateClusterStep().is_satisfied() is False

    def test_is_satisfied_false_when_name_missing(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.create_cluster._docker.run",
            return_value=_cp(stdout="othercluster  0/1\n"),
        ):
            assert CreateClusterStep().is_satisfied() is False


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

    def test_is_satisfied_true_when_kubectl_get_nodes_succeeds(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.wait_api._run",
            return_value=_cp(),
        ):
            assert WaitApiStep().is_satisfied() is True

    def test_is_satisfied_false_when_kubectl_fails(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.wait_api._run",
            return_value=_cp(returncode=1),
        ):
            assert WaitApiStep().is_satisfied() is False


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

    def test_jupyter_pre_builds_and_pushes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "docker_path", tmp_path / "docker")
        monkeypatch.setattr(settings, "repo_root", tmp_path)
        (tmp_path / "docker").mkdir()
        dockerfile = tmp_path / "docker" / "Dockerfile.jupyter"
        dockerfile.write_text("FROM scratch\n")

        with patch("hallm.cli.subcommands.cluster.setup_builders.jupyter.build_and_push") as mock:
            JupyterStep().pre()
        mock.assert_called_once_with(dockerfile, "jupyter", context=tmp_path)

    def test_jupyter_pre_raises_when_dockerfile_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "docker_path", tmp_path / "docker")
        monkeypatch.setattr(settings, "repo_root", tmp_path)

        with pytest.raises(SetupStepError, match="Jupyter Dockerfile not found"):
            JupyterStep().pre()

    def test_memory_mcp(self) -> None:
        step = MemoryMcpStep()
        assert isinstance(step.app, MemoryMcpApp)
        assert step.app.wait_target == "deploy/memory-mcp"


class TestSharedVolumesStep:
    def test_app_uses_manifest(self) -> None:
        step = SharedVolumesStep()
        assert isinstance(step.app, SharedVolumesApp)
        assert step.app.manifest_path == Path("shared-volumes.yaml")

    def test_is_satisfied_true_when_phase_is_bound(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.run",
            return_value=_cp(stdout="Bound"),
        ) as mock:
            assert SharedVolumesStep().is_satisfied() is True
        cmd = mock.call_args.args[0]
        assert cmd[:4] == ["kubectl", "get", "pvc", "shared-volumes"]
        assert "jsonpath={.status.phase}" in cmd

    def test_is_satisfied_false_when_phase_pending(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.run",
            return_value=_cp(stdout="Pending"),
        ):
            assert SharedVolumesStep().is_satisfied() is False

    def test_is_satisfied_false_when_kubectl_fails(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.run",
            return_value=_cp(returncode=1, stdout=""),
        ):
            assert SharedVolumesStep().is_satisfied() is False

    def test_post_validate_succeeds_when_pvc_binds(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.poll_until",
            return_value=True,
        ) as mock:
            SharedVolumesStep().post_validate()
        mock.assert_called_once()

    def test_post_validate_fails_when_pvc_never_binds(self) -> None:
        import typer

        with (
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.poll_until",
                return_value=False,
            ),
            pytest.raises(typer.Exit),
        ):
            SharedVolumesStep().post_validate()


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
