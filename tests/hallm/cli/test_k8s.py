"""Unit tests for the k8s CLI subcommand."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.k8s import app
from hallm.core.settings import settings

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture()
def k3d_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp k3d directory with a fake ollama manifest; patches settings paths."""
    k3d = tmp_path / "k3d"
    k3d.mkdir()
    (k3d / "ollama.yaml").write_text("apiVersion: v1\nkind: Namespace")
    monkeypatch.setattr(settings, "K3D_PATH", k3d)
    monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
    return k3d


@pytest.fixture()
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Creates a .env file in tmp_path and patches ROOT_PATH."""
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nBAZ=qux\n")
    monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
    return env


# ---------------------------------------------------------------------------
# sync-secrets
# ---------------------------------------------------------------------------


class TestSyncSecrets:
    def test_missing_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
        result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 1
        assert ".env not found" in result.output

    def test_kubectl_create_secret_fails(self, env_file: Path):
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="auth error")):
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 1
        assert "Failed to build" in result.output

    def test_kubectl_apply_fails(self, env_file: Path):
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="yaml: content"),  # kubectl create secret --dry-run
                _cp(returncode=1, stderr="apply err"),  # kubectl apply -f -
            ],
        ):
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 1
        assert "kubectl apply" in result.output

    def test_success(self, env_file: Path):
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="yaml: content"),  # kubectl create secret --dry-run
                _cp(),  # kubectl apply -f -
            ],
        ):
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 0
        assert "Done" in result.output


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_missing_manifest_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        empty_k3d = tmp_path / "k3d"
        empty_k3d.mkdir()
        monkeypatch.setattr(settings, "K3D_PATH", empty_k3d)
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "No manifest found" in result.output

    def test_success_no_label_resources(self, k3d_dir: Path):
        # preview + 4 label-sweep get calls + 1 delete
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="NAME\nnamespace/ollama"),  # kubectl get -f (preview)
                _cp(stdout=""),  # get pvc
                _cp(stdout=""),  # get secrets
                _cp(stdout=""),  # get configmaps
                _cp(stdout=""),  # get ingresses
                _cp(),  # kubectl delete -f (via _run)
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 0
        assert "removed" in result.output

    def test_success_with_label_resources(self, k3d_dir: Path):
        # preview + 4 label-sweep gets (1 finds a PVC) + 1 manifest delete + 4 sweep deletes
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="NAME\nnamespace/ollama"),  # preview
                _cp(stdout="persistentvolumeclaim/data"),  # get pvc → found
                _cp(stdout=""),  # get secrets
                _cp(stdout=""),  # get configmaps
                _cp(stdout=""),  # get ingresses
                _cp(),  # delete manifest (via _run)
                _cp(),  # delete pvc (via _run)
                _cp(),  # delete secrets (via _run)
                _cp(),  # delete configmaps (via _run)
                _cp(),  # delete ingresses (via _run)
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 0
        assert "removed" in result.output
        assert "persistentvolumeclaim/data" in result.output

    def test_confirmation_abort(self, k3d_dir: Path):
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout=""),  # preview
                _cp(stdout=""),  # get pvc
                _cp(stdout=""),  # get secrets
                _cp(stdout=""),  # get configmaps
                _cp(stdout=""),  # get ingresses
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="n\n")

        assert result.exit_code != 0

    def test_confirmation_proceed(self, k3d_dir: Path):
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout=""),  # preview
                _cp(stdout=""),  # get pvc
                _cp(stdout=""),  # get secrets
                _cp(stdout=""),  # get configmaps
                _cp(stdout=""),  # get ingresses
                _cp(),  # delete manifest
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="y\n")

        assert result.exit_code == 0

    def test_manifest_delete_fails(self, k3d_dir: Path):
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout=""),  # preview
                _cp(stdout=""),  # get pvc
                _cp(stdout=""),  # get secrets
                _cp(stdout=""),  # get configmaps
                _cp(stdout=""),  # get ingresses
                _cp(returncode=1, stderr="delete err"),  # delete manifest fails
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "Failed to delete" in result.output

    def test_custom_namespace(self, k3d_dir: Path):
        with patch("subprocess.run", side_effect=[_cp(stdout="")] * 5 + [_cp()]) as mock:
            result = runner.invoke(app, ["remove", "ollama", "--yes", "--namespace", "ollama"])

        assert result.exit_code == 0
        # preview call should include the custom namespace
        preview_args = mock.call_args_list[0][0][0]
        assert "ollama" in preview_args
