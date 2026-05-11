"""Direct tests for hallm.cli.subcommands.secrets internal Cerberus helpers.

These used to be exercised transitively via test_cluster.py / test_k8s_internals.py
(the setup command pipeline). After the cluster refactor the setup tests mock
these helpers, so we cover them directly here.
"""

import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from hallm.cli.subcommands import secrets as sec
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


class TestRestoreCerberusFromFiles:
    def test_applies_secret_and_issuer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pem = tmp_path / "ca.pem"
        key = tmp_path / "ca.key"
        pem.write_text("PEM")
        key.write_text("KEY")
        k8s = tmp_path / "k8s"
        (k8s / "adhoc").mkdir(parents=True)
        (k8s / "adhoc" / "cerberus-ca-issuer.yaml").write_text("kind: ClusterIssuer\n")
        monkeypatch.setattr(settings, "k8s_path", k8s)

        with (
            patch("hallm.cli.subcommands.secrets.kubectl.apply_from_cmd") as mock_apply_from_cmd,
            patch("hallm.cli.subcommands.secrets.kubectl.apply") as mock_apply,
        ):
            sec._restore_cerberus_from_files(pem, key)

        mock_apply_from_cmd.assert_called_once()
        mock_apply.assert_called_once()
        # Issuer manifest content was forwarded.
        assert "ClusterIssuer" in mock_apply.call_args.args[0]


class TestReadCerberusSecretData:
    def test_returns_stdout(self) -> None:
        with patch(
            "hallm.cli.subcommands.secrets._run_or_fail",
            return_value=_cp(stdout=" base64payload \n"),
        ):
            assert sec._read_cerberus_secret_data("tls.crt") == "base64payload"


class TestExportCerberusCa:
    def test_writes_decoded_cert_and_key(self, tmp_path: Path) -> None:
        pem = tmp_path / "ca.pem"
        key = tmp_path / "ca.key"
        cert_b64 = base64.b64encode(b"CERT").decode()
        key_b64 = base64.b64encode(b"KEY").decode()

        with (
            patch("hallm.cli.subcommands.secrets.kubectl.wait"),
            patch(
                "hallm.cli.subcommands.secrets._read_cerberus_secret_data",
                side_effect=[cert_b64, key_b64],
            ),
        ):
            sec._export_cerberus_ca(pem, key)

        assert pem.read_text() == "CERT"
        assert key.read_text() == "KEY"


class TestConfigureDockerRegistryCert:
    def test_writes_into_per_registry_certs_d(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Point HOME at tmp so ~/.config/docker/certs.d/... lives in the sandbox.
        monkeypatch.setenv("HOME", str(tmp_path))
        pem = tmp_path / "ca.pem"
        pem.write_text("PEM-DATA")

        sec._configure_docker_registry_cert(pem)

        target = tmp_path / ".config" / "docker" / "certs.d" / "unregistry.hallm.local" / "ca.crt"
        assert target.read_text() == "PEM-DATA"


class TestGetCertificate:
    def test_empty_cert_fails(
        self, secrets_dir: Path, runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with patch(
            "hallm.cli.subcommands.secrets._read_cerberus_secret_data",
            side_effect=["", ""],
        ):
            result = runner.invoke(sec.app, ["get-certificate"])
        assert result.exit_code == 1
        assert "is empty" in result.output

    def test_empty_key_fails(
        self, secrets_dir: Path, runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cert_b64 = base64.b64encode(b"CERT").decode()
        with patch(
            "hallm.cli.subcommands.secrets._read_cerberus_secret_data",
            side_effect=[cert_b64, ""],
        ):
            result = runner.invoke(sec.app, ["get-certificate"])
        assert result.exit_code == 1
        assert "is empty" in result.output

    def test_happy_path(self, secrets_dir: Path, runner, monkeypatch: pytest.MonkeyPatch) -> None:
        cert_b64 = base64.b64encode(b"CERT").decode()
        key_b64 = base64.b64encode(b"KEY").decode()
        monkeypatch.setenv("HOME", str(secrets_dir.parent))
        with patch(
            "hallm.cli.subcommands.secrets._read_cerberus_secret_data",
            side_effect=[cert_b64, key_b64],
        ):
            result = runner.invoke(sec.app, ["get-certificate"])
        assert result.exit_code == 0
        assert (secrets_dir / "cerberus-ca.pem").read_text() == "CERT"
        assert (secrets_dir / "cerberus-ca.key").read_text() == "KEY"
