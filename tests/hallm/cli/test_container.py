"""Unit tests for hallm.cli.subcommands.container."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.container import app
from hallm.core.settings import settings as _settings
from tests.mocks import completed_process as _cp
from tests.utils import write_dockerfile
from tests.utils import write_manifest


class TestPublish:
    def test_dockerfile_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        result = runner.invoke(app, ["publish", "myimage"])
        assert result.exit_code == 1
        assert "Dockerfile not found" in result.output

    def test_build_push_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="buildx error")):
            result = runner.invoke(app, ["publish", "myimage"])
        assert result.exit_code == 1
        assert "Build/push failed for myimage" in result.output

    def test_publish_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["publish", "myimage"])
        assert result.exit_code == 0
        assert "[OK]" in result.output
        assert "myimage" in result.output
        assert "latest" in result.output
        # Single buildx invocation — no separate push step.
        assert mock.call_count == 1
        cmd = mock.call_args_list[0][0][0]
        assert cmd[:3] == ["docker", "buildx", "build"]
        assert "--network=host" in cmd
        assert "--output" in cmd and "type=registry" in cmd
        assert "--provenance=false" in cmd and "--sbom=false" in cmd

    def test_publish_path_derives_name_from_filename(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        dockerfile = tmp_path / "Dockerfile.myimage"
        dockerfile.write_text("FROM scratch\n")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["publish", str(dockerfile)])
        assert result.exit_code == 0
        assert "myimage" in result.output
        cmd = mock.call_args_list[0][0][0]
        # Build context is the dockerfile's parent.
        assert cmd[-1] == str(tmp_path.resolve())
        # Image tag was derived from filename.
        assert "unregistry.hallm.local/hallm/myimage:latest" in cmd

    def test_publish_path_with_name_override(self, tmp_path: Path, runner: CliRunner) -> None:
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM scratch\n")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["publish", str(dockerfile), "--name", "custom"])
        assert result.exit_code == 0
        assert "custom" in result.output
        cmd = mock.call_args_list[0][0][0]
        assert "unregistry.hallm.local/hallm/custom:latest" in cmd

    def test_publish_path_unparseable_filename_requires_name(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM scratch\n")
        result = runner.invoke(app, ["publish", str(dockerfile)])
        assert result.exit_code == 1
        assert "Cannot derive image name" in result.output

    def test_publish_name_with_override_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        result = runner.invoke(app, ["publish", "myimage", "--name", "custom"])
        assert result.exit_code == 1
        assert "--name is only valid" in result.output


class TestDeploy:
    def test_manifest_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "k8s_path", k8s)
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        result = runner.invoke(app, ["deploy", "ollama"])
        assert result.exit_code == 1
        assert "No manifest found" in result.output

    def test_deploy_no_dockerfile_skips_build(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_manifest(tmp_path, "ollama")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "k8s_path", tmp_path / "k8s")
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["deploy", "ollama"])
        assert result.exit_code == 0
        assert "[OK]" in result.output
        # Only the kubectl apply call — no docker build/push
        apply_cmd = mock.call_args_list[0][0][0]
        assert apply_cmd == ["kubectl", "apply", "-f", "-"]

    def test_deploy_with_dockerfile_builds_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_manifest(tmp_path, "ollama")
        write_dockerfile(tmp_path, "ollama")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "k8s_path", tmp_path / "k8s")
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["deploy", "ollama"])
        assert result.exit_code == 0
        # First call should be docker build
        first_cmd = mock.call_args_list[0][0][0]
        assert first_cmd[0] == "docker" and "build" in first_cmd
        # Last call should be kubectl apply
        last_cmd = mock.call_args_list[-1][0][0]
        assert last_cmd == ["kubectl", "apply", "-f", "-"]

    def test_deploy_with_manifest_path_skips_repo_resolution(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        manifest = tmp_path / "stand-alone.yaml"
        manifest.write_text("apiVersion: v1\nkind: Namespace\nmetadata:\n  name: solo\n")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["deploy", str(manifest), "--no-build"])
        assert result.exit_code == 0
        assert "stand-alone deployed" in result.output
        # Single kubectl apply — no docker build since target is a path
        assert mock.call_count == 1
        apply_cmd = mock.call_args_list[0].args[0]
        assert apply_cmd == ["kubectl", "apply", "-f", "-"]

    def test_deploy_no_build_flag_skips_publish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        write_manifest(tmp_path, "ollama")
        write_dockerfile(tmp_path, "ollama")
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "k8s_path", tmp_path / "k8s")
        monkeypatch.setattr(_settings, "docker_path", tmp_path / "docker")
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["deploy", "ollama", "--no-build"])
        assert result.exit_code == 0
        # Only the kubectl apply — no docker calls
        apply_cmd = mock.call_args_list[0][0][0]
        assert apply_cmd == ["kubectl", "apply", "-f", "-"]
        assert mock.call_count == 1


class TestRemove:
    def test_missing_manifest_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        empty = tmp_path / "k8s"
        empty.mkdir()
        monkeypatch.setattr(_settings, "repo_root", tmp_path)
        monkeypatch.setattr(_settings, "k8s_path", empty)

        result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "No manifest found" in result.output

    def test_success_no_label_resources(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="NAME\nnamespace/ollama"),
                _cp(stdout=""),
                _cp(stdout=""),
                _cp(stdout=""),
                _cp(stdout=""),
                _cp(),
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 0
        assert "removed" in result.output

    def test_success_with_label_resources(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="NAME\nnamespace/ollama"),
                _cp(stdout="persistentvolumeclaim/data"),
                _cp(stdout=""),
                _cp(stdout=""),
                _cp(stdout=""),
                _cp(),
                _cp(),
                _cp(),
                _cp(),
                _cp(),
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 0
        assert "removed" in result.output
        assert "persistentvolumeclaim/data" in result.output

    def test_confirmation_abort(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5,
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="n\n")

        assert result.exit_code != 0

    def test_confirmation_proceed(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5 + [_cp()],
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="y\n")

        assert result.exit_code == 0

    def test_manifest_delete_fails(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5 + [_cp(returncode=1, stderr="delete err")],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "Failed to delete" in result.output

    def test_remove_with_manifest_path_works_without_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        from hallm.cli.subcommands import container as _container

        manifest = tmp_path / "stand-alone.yaml"
        manifest.write_text("apiVersion: v1\nkind: Namespace\nmetadata:\n  name: solo\n")
        # find_repo returns None — exercises the "no repo discoverable" fallback for the
        # 'Resources to remove (from <abs path>)' line.
        monkeypatch.setattr(_container.workspace, "find_repo", lambda: None)
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5 + [_cp()],
        ):
            result = runner.invoke(app, ["remove", str(manifest), "--yes"])
        assert result.exit_code == 0
        assert str(manifest) in result.output

    def test_label_resources_with_embedded_empty_line(
        self, k8s_dir: Path, runner: CliRunner
    ) -> None:
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="NAME\nnamespace/ollama"),  # preview
                _cp(stdout="pvc/a\n\npvc/b"),  # pvc: interior empty line
                _cp(stdout=""),  # secrets
                _cp(stdout=""),  # configmaps
                _cp(stdout=""),  # ingresses
                _cp(),  # kubectl delete manifest
                _cp(),  # delete by label pvc
                _cp(),  # delete by label secrets
                _cp(),  # delete by label configmaps
                _cp(),  # delete by label ingresses
            ],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])
        assert result.exit_code == 0
        assert "pvc/a" in result.output
        assert "pvc/b" in result.output

    def test_custom_namespace(self, k8s_dir: Path, runner: CliRunner) -> None:
        with patch("subprocess.run", side_effect=[_cp(stdout="")] * 5 + [_cp()]) as mock:
            result = runner.invoke(app, ["remove", "ollama", "--yes", "--namespace", "ollama"])

        assert result.exit_code == 0
        preview_args = mock.call_args_list[0][0][0]
        assert "ollama" in preview_args
