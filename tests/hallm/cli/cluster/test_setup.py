"""End-to-end tests for the `hallm cluster setup` command."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings


@pytest.fixture
def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # NOTE: K8S_PATH is NOT monkeypatched — Apps' manifest_path attributes are
    # bound at import time against the real k8s/ tree, and the builder's claim
    # check needs the same paths to match. Subprocess/kubectl calls are all
    # mocked, so no real apply runs.
    monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path / "secrets")
    monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", tmp_path / "mnt")
    monkeypatch.setattr(settings, "DOCKER_CONTEXT", "hallm")


class TestSetupCommand:
    def _patch_all_runs(self):
        """Patch every Step subroutine so nothing actually touches the host."""
        from contextlib import ExitStack

        from tests.mocks import completed_process as _cp

        stack = ExitStack()
        # Top-level pipeline subprocess / docker calls.
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.base._docker.run",
                return_value=_cp(),
            )
        )
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces._run",
                return_value=_cp(),
            )
        )
        # Each concrete Step's side-effecting helper.
        for path in (
            "hallm.cli.subcommands.cluster.setup_builders.preflight._run_preflight",
            "hallm.cli.subcommands.cluster.setup_builders.mount_storage._mount_storage",
            "hallm.cli.subcommands.cluster.setup_builders.create_cluster._docker.run_or_fail",
            "hallm.cli.subcommands.cluster.setup_builders.sync_secrets._secrets._sync_secrets",
            "hallm.cli.subcommands.cluster.setup_builders.trust_docker_ca._secrets._configure_docker_registry_cert",
            "hallm.cli.subcommands.cluster.setup_builders.cerberus_pki._secrets._restore_cerberus_from_files",
            "hallm.cli.subcommands.cluster.setup_builders.cerberus_pki._secrets._export_cerberus_ca",
            "hallm.cli.subcommands.cluster.setup_builders.postgres._db._run_bootstrap",
            "hallm.cli.subcommands.cluster.setup_builders.signoz._signoz._run_bootstrap",
            "hallm.cli.subcommands.cluster.setup_builders.headlamp._build_plugin",
            "hallm.cli.subcommands.cluster.setup_builders.headlamp._pack_configmap",
            "hallm.cli.subcommands.cluster.setup_builders.base.kubectl.apply",
            "hallm.cli.subcommands.cluster.setup_builders.base.kubectl.apply_url",
            "hallm.cli.subcommands.cluster.setup_builders.base.kubectl.wait",
        ):
            stack.enter_context(patch(path))
        # is_satisfied() probes — keep them returning False so the run() path
        # exercises every Step rather than being short-circuited (and so we
        # don't shell out to a real `kubectl` that the test container lacks).
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.base.kubectl.probe",
                return_value=False,
            )
        )
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.wait_api._run",
                return_value=_cp(returncode=1),
            )
        )
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.wait_api.poll_until",
                return_value=True,
            )
        )
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.poll_until",
                return_value=True,
            )
        )
        stack.enter_context(
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.shared_volumes.run",
                return_value=_cp(stdout="Bound"),
            )
        )
        return stack

    def test_happy_path_signoz_disabled(self, runner, _setup_env, monkeypatch) -> None:
        monkeypatch.setattr(settings, "signoz_enabled", False)
        with self._patch_all_runs():
            result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0, result.output
        assert "Cluster is ready" in result.output

    def test_happy_path_signoz_enabled(self, runner, _setup_env, monkeypatch) -> None:
        monkeypatch.setattr(settings, "signoz_enabled", True)
        with self._patch_all_runs():
            result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "Bootstrapping SigNoz" in result.output

    def test_custom_context_overrides_setting(self, runner, _setup_env, monkeypatch) -> None:
        monkeypatch.setattr(settings, "signoz_enabled", False)
        with self._patch_all_runs():
            result = runner.invoke(app, ["setup", "--context", "default"])
        assert result.exit_code == 0
        assert settings.DOCKER_CONTEXT == "default"
