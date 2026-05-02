"""Unit tests for the secrets CLI subcommand (apply + prepare)."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.secrets import app
from hallm.core.settings import settings

runner = CliRunner()


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture()
def secrets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sd = tmp_path / ".hallm"
    sd.mkdir()
    monkeypatch.setattr(settings, "SECRETS_PATH", sd)
    return sd


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_no_env_files(self, secrets_dir: Path) -> None:
        result = runner.invoke(app, ["apply"])
        assert result.exit_code == 0
        assert "No .env files found" in result.output

    def test_creates_secrets_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "new-hallm"
        monkeypatch.setattr(settings, "SECRETS_PATH", missing)
        result = runner.invoke(app, ["apply"])

        assert missing.exists()
        assert result.exit_code == 0

    def test_named_secret_kubectl_create_fails(self, secrets_dir: Path) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="auth error")):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert "Failed to build" in result.output

    def test_named_secret_kubectl_apply_fails(self, secrets_dir: Path) -> None:
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

    def test_named_secret_success(self, secrets_dir: Path) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "myapp.env → Secret 'myapp'" in result.output
        assert "Done" in result.output

    def test_dotenv_maps_to_hallm_env(self, secrets_dir: Path) -> None:
        (secrets_dir / ".env").write_text("FOO=bar\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert ".env → Secret 'hallm-env'" in result.output

    def test_multiple_secrets_synced(self, secrets_dir: Path) -> None:
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
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
        result = runner.invoke(app, ["prepare"])
        assert result.exit_code == 1
        assert "No .env found" in result.output

    def test_creates_secrets_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("ENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        result = runner.invoke(app, ["prepare"])

        assert result.exit_code == 0
        assert (secrets_dir / ".env").exists()
        assert "Done" in result.output

    def test_rewrites_https_url(
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("GOTIFY_URL=https://gotify.hallm.local\nENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "http://gotify.default.svc.cluster.local" in out
        assert "hallm.local" not in out

    def test_rewrites_http_url(
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("RUSTFS_ENDPOINT=http://rustfs.hallm.local:9000\nENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "http://rustfs.default.svc.cluster.local:9000" in out

    def test_rewrites_bare_hostname(
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("DATABASE_LOCAL_HOST=postgres.hallm.local\nENVIRONMENT=localhost\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "postgres.default.svc.cluster.local" in out
        assert "hallm.local" not in out

    def test_sets_environment_kubernetes(
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text("ENVIRONMENT=localhost\nDEBUG=false\n")
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "ENVIRONMENT=kubernetes" in out
        assert "ENVIRONMENT=localhost" not in out

    def test_preserves_existing_k8s_urls(
        self, tmp_path: Path, secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / ".env"
        src.write_text(
            "OTEL_ENDPOINT=http://signoz-otel-collector.signoz.svc.cluster.local:4317\n"
            "ENVIRONMENT=localhost\n"
        )
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        runner.invoke(app, ["prepare"])

        out = (secrets_dir / ".env").read_text()
        assert "signoz-otel-collector.signoz.svc.cluster.local:4317" in out
