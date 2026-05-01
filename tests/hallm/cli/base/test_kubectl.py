"""Unit tests for hallm.cli.base.kubectl."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from hallm.cli.base import kubectl


def _cp(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_success_does_not_raise(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.apply("apiVersion: v1\n")

    def test_echoes_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.apply("...", label="Cerberus PKI")
        assert "Cerberus PKI" in capsys.readouterr().out

    def test_default_label_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.apply("...")
        assert "manifest" in capsys.readouterr().out

    def test_pipes_manifest_as_stdin(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.apply("my: yaml\n", label="test")
        _, kwargs = mock.call_args
        assert kwargs["input"] == "my: yaml\n"

    def test_uses_kubectl_apply_stdin_args(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.apply("x: 1\n")
        cmd = mock.call_args.args[0]
        assert cmd == ["kubectl", "apply", "-f", "-"]

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="denied")):
            with pytest.raises(typer.Exit):
                kubectl.apply("bad: yaml\n")

    def test_failure_exit_code_is_1(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1)):
            with pytest.raises(typer.Exit) as exc_info:
                kubectl.apply("x: 1\n")
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# apply_url
# ---------------------------------------------------------------------------


class TestApplyUrl:
    def test_success_does_not_raise(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.apply_url("https://example.com/manifest.yaml")

    def test_passes_url_to_kubectl(self) -> None:
        url = "https://example.com/cert-manager.yaml"
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.apply_url(url)
        cmd = mock.call_args.args[0]
        assert url in cmd
        assert "kubectl" in cmd
        assert "apply" in cmd

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="not found")):
            with pytest.raises(typer.Exit):
                kubectl.apply_url("https://example.com/missing.yaml")

    def test_failure_exit_code_is_1(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1)):
            with pytest.raises(typer.Exit) as exc_info:
                kubectl.apply_url("https://example.com/x.yaml")
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# apply_from_cmd
# ---------------------------------------------------------------------------


class TestApplyFromCmd:
    def test_success_does_not_raise(self) -> None:
        # Two subprocess.run calls: source_cmd then kubectl apply.
        with patch("subprocess.run", side_effect=[_cp(stdout="k: v\n"), _cp()]):
            kubectl.apply_from_cmd("Secret 'hallm-env'", ["kubectl", "create", "secret"])

    def test_pipes_source_stdout_as_manifest(self) -> None:
        generated = "apiVersion: v1\nkind: Secret\n"
        with patch("subprocess.run", side_effect=[_cp(stdout=generated), _cp()]) as mock:
            kubectl.apply_from_cmd("my-secret", ["kubectl", "create", "secret"])
        apply_call = mock.call_args_list[1]
        assert apply_call.kwargs["input"] == generated

    def test_source_cmd_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            with pytest.raises(typer.Exit):
                kubectl.apply_from_cmd("secret", ["bad", "cmd"])

    def test_apply_failure_raises_exit(self) -> None:
        with patch("subprocess.run", side_effect=[_cp(stdout="k: v\n"), _cp(returncode=1)]):
            with pytest.raises(typer.Exit):
                kubectl.apply_from_cmd("secret", ["kubectl", "create", "secret"])


# ---------------------------------------------------------------------------
# wait
# ---------------------------------------------------------------------------


class TestWait:
    def test_success_does_not_raise(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.wait("deploy/cert-manager-webhook", "Available", namespace="cert-manager")

    def test_includes_condition_flag(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Ready")
        cmd = mock.call_args.args[0]
        assert "--for=condition=Ready" in cmd

    def test_includes_resource(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Available")
        cmd = mock.call_args.args[0]
        assert "deploy/foo" in cmd

    def test_default_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Available")
        cmd = mock.call_args.args[0]
        assert "-n" in cmd
        assert cmd[cmd.index("-n") + 1] == "default"

    def test_custom_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Available", namespace="kube-system")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "kube-system"

    def test_default_timeout(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Available")
        cmd = mock.call_args.args[0]
        assert "--timeout=60s" in cmd

    def test_custom_timeout(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.wait("deploy/foo", "Available", timeout="120s")
        cmd = mock.call_args.args[0]
        assert "--timeout=120s" in cmd

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1)):
            with pytest.raises(typer.Exit):
                kubectl.wait("deploy/foo", "Available")

    def test_failure_exit_code_is_1(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1)):
            with pytest.raises(typer.Exit) as exc_info:
                kubectl.wait("deploy/foo", "Available")
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# rollout_restart
# ---------------------------------------------------------------------------


class TestRolloutRestart:
    def test_success_does_not_raise(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.rollout_restart("deploy/hallm")

    def test_command_includes_resource(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.rollout_restart("deploy/hallm")
        cmd = mock.call_args.args[0]
        assert "rollout" in cmd
        assert "restart" in cmd
        assert "deploy/hallm" in cmd

    def test_default_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.rollout_restart("deploy/hallm")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "default"

    def test_custom_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.rollout_restart("deploy/hallm", namespace="ollama")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "ollama"

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="not found")):
            with pytest.raises(typer.Exit):
                kubectl.rollout_restart("deploy/hallm")

    def test_failure_exit_code_is_1(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1)):
            with pytest.raises(typer.Exit) as exc_info:
                kubectl.rollout_restart("deploy/hallm")
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# delete_manifest
# ---------------------------------------------------------------------------


class TestDeleteManifest:
    def test_success_does_not_raise(self, tmp_path: Path) -> None:
        manifest = tmp_path / "ollama.yaml"
        manifest.write_text("kind: Deployment\n")
        with patch("subprocess.run", return_value=_cp()):
            kubectl.delete_manifest(manifest)

    def test_passes_manifest_path(self, tmp_path: Path) -> None:
        manifest = tmp_path / "postgres.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest(manifest)
        cmd = mock.call_args.args[0]
        assert str(manifest) in cmd

    def test_uses_delete_f_flag(self, tmp_path: Path) -> None:
        manifest = tmp_path / "x.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest(manifest)
        cmd = mock.call_args.args[0]
        assert "delete" in cmd
        assert "-f" in cmd

    def test_includes_ignore_not_found(self, tmp_path: Path) -> None:
        manifest = tmp_path / "x.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest(manifest)
        cmd = mock.call_args.args[0]
        assert "--ignore-not-found" in cmd

    def test_default_namespace(self, tmp_path: Path) -> None:
        manifest = tmp_path / "x.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest(manifest)
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "default"

    def test_custom_namespace(self, tmp_path: Path) -> None:
        manifest = tmp_path / "x.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest(manifest, namespace="ollama")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "ollama"

    def test_accepts_string_path(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_manifest("/tmp/manifest.yaml")
        cmd = mock.call_args.args[0]
        assert "/tmp/manifest.yaml" in cmd

    def test_failure_raises_exit(self, tmp_path: Path) -> None:
        manifest = tmp_path / "x.yaml"
        manifest.write_text("")
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            with pytest.raises(typer.Exit):
                kubectl.delete_manifest(manifest)


# ---------------------------------------------------------------------------
# delete_by_label
# ---------------------------------------------------------------------------


class TestGetJson:
    def test_returns_parsed_dict(self) -> None:
        with patch("subprocess.run", return_value=_cp(stdout='{"a": 1}')):
            assert kubectl.get_json(["clusterissuer", "cerberus-ca"]) == {"a": 1}

    def test_returns_parsed_list(self) -> None:
        with patch("subprocess.run", return_value=_cp(stdout="[1, 2, 3]")):
            assert kubectl.get_json(["pods"]) == [1, 2, 3]

    def test_returns_none_on_kubectl_failure(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="not found")):
            assert kubectl.get_json(["bogus"]) is None

    def test_returns_none_on_parse_error(self) -> None:
        with patch("subprocess.run", return_value=_cp(stdout="not-json")):
            assert kubectl.get_json(["pods"]) is None


class TestDeleteByLabel:
    def test_success_does_not_raise(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            kubectl.delete_by_label("persistentvolumeclaims", "app=ollama")

    def test_command_includes_kind_and_label(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_by_label("secrets", "app=postgres")
        cmd = mock.call_args.args[0]
        assert "secrets" in cmd
        assert "app=postgres" in cmd
        assert "-l" in cmd

    def test_includes_ignore_not_found(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_by_label("configmaps", "app=hallm")
        cmd = mock.call_args.args[0]
        assert "--ignore-not-found" in cmd

    def test_default_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_by_label("secrets", "app=foo")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "default"

    def test_custom_namespace(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            kubectl.delete_by_label("secrets", "app=foo", namespace="ollama")
        cmd = mock.call_args.args[0]
        assert cmd[cmd.index("-n") + 1] == "ollama"

    def test_failure_warns_instead_of_raising(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            kubectl.delete_by_label("ingresses", "app=foo")
        assert "WARNING" in capsys.readouterr().err

    def test_failure_does_not_raise_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            kubectl.delete_by_label("ingresses", "app=foo")
