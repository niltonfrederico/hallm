"""Unit tests for the secrets CLI subcommand (apply, prepare, get-certificate)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.secrets import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp

_PATCH_DOCKER_CERT = patch("hallm.cli.subcommands.secrets._configure_docker_registry_cert")


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_no_env_files(self, secrets_dir: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["apply"])
        assert result.exit_code == 0
        assert "No .env files found" in result.output

    def test_creates_secrets_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        missing = tmp_path / "new-hallm"
        monkeypatch.setattr(settings, "SECRETS_PATH", missing)
        result = runner.invoke(app, ["apply"])

        assert missing.exists()
        assert result.exit_code == 0

    def test_named_secret_kubectl_create_fails(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="auth error")):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert "Failed to build" in result.output

    def test_named_secret_kubectl_apply_fails(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="yaml: content"),
                _cp(returncode=1, stderr="apply err"),
            ],
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert "kubectl apply" in result.output

    def test_named_secret_success(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "myapp.env → Secret 'myapp'" in result.output
        assert "Done" in result.output

    def test_dotenv_maps_to_hallm_env(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / ".env").write_text("FOO=bar\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert ".env → Secret 'hallm-env'" in result.output

    def test_namespaced_filename(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / "signoz.otel.env").write_text("X=1\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ) as mock_run:
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "signoz.otel.env → Secret 'otel' in namespace 'signoz'" in result.output
        create_cmd = mock_run.call_args_list[0].args[0]
        assert "otel" in create_cmd
        assert "--namespace" in create_cmd
        assert create_cmd[create_cmd.index("--namespace") + 1] == "signoz"

    def test_multiple_secrets_synced(self, secrets_dir: Path, runner: CliRunner) -> None:
        (secrets_dir / "alpha.env").write_text("A=1\n")
        (secrets_dir / "beta.env").write_text("B=2\n")
        (secrets_dir / ".env").write_text("C=3\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="y"), _cp()] * 3,
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "alpha.env → Secret 'alpha'" in result.output
        assert "beta.env → Secret 'beta'" in result.output
        assert ".env → Secret 'hallm-env'" in result.output


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


class TestPrepare:
    def test_missing_workspace_env_fails(
        self,
        tmp_path: Path,
        secrets_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
    ) -> None:
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
        result = runner.invoke(app, ["prepare"])
        assert result.exit_code == 1
        assert "No .env found" in result.output

    def test_creates_secrets_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("ENVIRONMENT=localhost\n")
        missing = tmp_path / "new-hallm"
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
        monkeypatch.setattr(settings, "SECRETS_PATH", missing)

        result = runner.invoke(app, ["prepare"])

        assert result.exit_code == 0
        assert missing.exists()

    def test_writes_dest_env(
        self,
        tmp_path: Path,
        secrets_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("ENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        result = runner.invoke(app, ["prepare"])

        assert result.exit_code == 0
        assert (secrets_dir / ".env").exists()
        assert "Done" in result.output

    @pytest.mark.parametrize(
        ("input_line", "expected_substring", "absent_substring"),
        [
            (
                "GOTIFY_URL=https://gotify.hallm.local",
                "http://gotify.default.svc.cluster.local",
                "hallm.local",
            ),
            (
                "RUSTFS_ENDPOINT=http://rustfs.hallm.local:9000",
                "http://rustfs.default.svc.cluster.local:9000",
                None,
            ),
            (
                "DATABASE_HOST=postgres.hallm.local",
                "postgres.default.svc.cluster.local",
                "hallm.local",
            ),
            (
                "OTEL_ENDPOINT=http://signoz-otel-collector.signoz.svc.cluster.local:4317",
                "signoz-otel-collector.signoz.svc.cluster.local:4317",
                None,
            ),
        ],
        ids=["https", "http", "bare-hostname", "preserve-existing-k8s-url"],
    )
    def test_url_rewrites(
        self,
        tmp_path: Path,
        secrets_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        input_line: str,
        expected_substring: str,
        absent_substring: str | None,
    ) -> None:
        src = tmp_path / ".env"
        src.write_text(f"{input_line}\nENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert expected_substring in out
        if absent_substring is not None:
            assert absent_substring not in out

    def test_sets_environment_kubernetes(
        self,
        tmp_path: Path,
        secrets_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("ENVIRONMENT=localhost\nDEBUG=false\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "ENVIRONMENT=kubernetes" in out
        assert "ENVIRONMENT=localhost" not in out


# ---------------------------------------------------------------------------
# get-certificate
# ---------------------------------------------------------------------------


class TestGetCertificate:
    def test_success(self, tmp_path: Path, runner: CliRunner, cert_b64: str, key_b64: str) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch(
                "subprocess.run",
                side_effect=[_cp(stdout=cert_b64), _cp(stdout=key_b64)],
            ),
            patch.object(settings, "SECRETS_PATH", sd),
            _PATCH_DOCKER_CERT as mock_cert,
        ):
            result = runner.invoke(app, ["get-certificate"])

        assert result.exit_code == 0
        assert "Cert →" in result.output
        assert "Key  →" in result.output
        assert "BEGIN CERTIFICATE" in (sd / "cerberus-ca.pem").read_text()
        assert "BEGIN EC PRIVATE KEY" in (sd / "cerberus-ca.key").read_text()
        mock_cert.assert_called_once_with(sd / "cerberus-ca.pem")

    def test_kubectl_fails(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="not found")):
            result = runner.invoke(app, ["get-certificate"])
        assert result.exit_code == 1
        assert "cerberus-ca-secret" in result.output

    def test_empty_cert(self, tmp_path: Path, runner: CliRunner) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch("subprocess.run", return_value=_cp(returncode=0, stdout="")),
            patch.object(settings, "SECRETS_PATH", sd),
        ):
            result = runner.invoke(app, ["get-certificate"])
        assert result.exit_code == 1
        assert "empty" in result.output

    def test_empty_key(self, tmp_path: Path, runner: CliRunner, cert_b64: str) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch("subprocess.run", side_effect=[_cp(stdout=cert_b64), _cp(stdout="")]),
            patch.object(settings, "SECRETS_PATH", sd),
        ):
            result = runner.invoke(app, ["get-certificate"])
        assert result.exit_code == 1
        assert "empty" in result.output
