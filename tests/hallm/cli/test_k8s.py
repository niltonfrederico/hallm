"""Unit tests for the merged k8s CLI subcommand (cluster lifecycle + ops)."""

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
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


def _socket_cm(*args: object, **kwargs: object) -> MagicMock:
    """Return a MagicMock that works as a context manager (open socket)."""
    return MagicMock()


@pytest.fixture()
def k8s_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp k8s manifests directory with a fake ollama manifest."""
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "ollama.yaml").write_text("apiVersion: v1\nkind: Namespace")
    monkeypatch.setattr(settings, "K8S_PATH", k8s)
    monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)
    return k8s


@pytest.fixture()
def secrets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Creates ~/.hallm-equivalent dir in tmp_path and patches SECRETS_PATH."""
    sd = tmp_path / ".hallm"
    sd.mkdir()
    monkeypatch.setattr(settings, "SECRETS_PATH", sd)
    return sd


_CLUSTER_LIST_OK = json.dumps([{"name": "hallm", "serversRunning": 1}])
_NODES_OK = json.dumps({"items": [{"status": {"allocatable": {"amd.com/gpu": "1"}}}]})
_DS_OK = json.dumps(
    {
        "items": [
            {
                "metadata": {"name": "amdgpu-device-plugin"},
                "status": {"desiredNumberScheduled": 1, "numberReady": 1},
            }
        ]
    }
)
_ISSUER_OK = json.dumps({"status": {"conditions": [{"type": "Ready", "status": "True"}]}})

_CERT_B64 = base64.b64encode(
    b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n"
).decode()
_KEY_B64 = base64.b64encode(
    b"-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----\n"
).decode()


def _healthcheck_happy_path_calls() -> list[subprocess.CompletedProcess]:
    """Ordered subprocess.run return values for a fully passing healthcheck."""
    return [
        _cp(stdout=_CLUSTER_LIST_OK),  # k3d cluster list
        _cp(stdout=_NODES_OK),  # kubectl get node
        _cp(stdout=_DS_OK),  # kubectl get ds -n kube-system
        _cp(stdout=_ISSUER_OK),  # kubectl get clusterissuer cerberus-ca
        _cp(),  # GPU smoke: kubectl apply
        _cp(stdout="Succeeded"),  # GPU smoke: kubectl get pod phase
        _cp(),  # GPU smoke: kubectl delete pod
        _cp(),  # DNS smoke: kubectl apply
        _cp(stdout="Running"),  # DNS smoke: kubectl get pods phase
        _cp(),  # DNS smoke: cleanup
    ]


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

_PATCH_MOUNT = patch("hallm.cli.subcommands.k8s._mount_storage")
_PATCH_PREFLIGHT = patch("hallm.cli.subcommands.k8s._run_preflight")


class TestSetup:
    def test_success(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp(stdout=_CERT_B64)) as mock,
            patch("hallm.cli.subcommands.k8s._manifest", return_value="cerberus: yaml"),
            patch("hallm.cli.subcommands.k8s._install_signoz"),
            patch("hallm.cli.subcommands.k8s._apply_all_service_manifests"),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "Done" in result.output
        assert mock.call_count == 8

    def test_k3d_create_fails(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp(returncode=1, stderr="boom")),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "k3d cluster create failed" in result.output

    def test_device_plugin_fails(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", side_effect=[_cp(), _cp(returncode=1, stderr="dp fail")]),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "kubectl apply failed" in result.output

    def test_cert_manager_fails(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", side_effect=[_cp(), _cp(), _cp(returncode=1)]),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "cert-manager" in result.output

    def test_webhook_wait_fails(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", side_effect=[_cp(), _cp(), _cp(), _cp(returncode=1)]),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "webhook" in result.output

    def test_cerberus_apply_fails(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch(
                "subprocess.run",
                side_effect=[_cp()] * 4 + [_cp(returncode=1, stderr="cerb")],
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="cerberus: yaml"),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "Cerberus PKI" in result.output

    def test_cerberus_restored_from_existing_files(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        (secrets / "cerberus-ca.pem").write_text("CERT")
        (secrets / "cerberus-ca.key").write_text("KEY")
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp()) as mock,
            patch("hallm.cli.subcommands.k8s._install_signoz"),
            patch("hallm.cli.subcommands.k8s._apply_all_service_manifests"),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "Restoring" in result.output
        # 4 pre-cerberus + create-secret dry-run + apply secret + apply issuer
        assert mock.call_count == 7


# ---------------------------------------------------------------------------
# nuke
# ---------------------------------------------------------------------------


class TestNuke:
    def test_yes_flag_success(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 0
        assert "deleted" in result.output
        mock.assert_called_once()

    def test_yes_flag_delete_fails(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 1
        assert "delete failed" in result.output

    def test_confirmation_abort(self) -> None:
        result = runner.invoke(app, ["nuke"], input="n\n")
        assert result.exit_code != 0

    def test_confirmation_proceed(self) -> None:
        with patch("subprocess.run", return_value=_cp()):
            result = runner.invoke(app, ["nuke"], input="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_volumes_flag_wipes_storage(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["nuke", "--yes", "--volumes"])

        assert result.exit_code == 0
        assert "deleted" in result.output
        assert mock.call_count == 2
        rm_args = mock.call_args_list[1][0][0]
        assert rm_args[:3] == ["sudo", "rm", "-rf"]

    def test_volumes_flag_included_in_confirmation_message(self) -> None:
        result = runner.invoke(app, ["nuke", "--volumes"], input="n\n")
        assert "data in" in result.output
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# healthcheck
# ---------------------------------------------------------------------------


class TestHealthcheck:
    @staticmethod
    def _urlopen_ok() -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=MagicMock(status=200))
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_all_checks_pass(self) -> None:
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_cluster_not_running_fails_exit(self) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout=json.dumps([]))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_not_visible_fails_exit(self) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[1] = _cp(stdout=json.dumps({"items": []}))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_port_not_reachable_fails_exit(self) -> None:
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch(
                "hallm.cli.subcommands.k8s.socket.create_connection",
                side_effect=OSError("refused"),
            ),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_smoke_pod_apply_fails(self) -> None:
        calls = [
            _cp(stdout=_CLUSTER_LIST_OK),
            _cp(stdout=_NODES_OK),
            _cp(stdout=_DS_OK),
            _cp(stdout=_ISSUER_OK),
            _cp(returncode=1, stderr="apply fail"),  # GPU smoke apply fails
            _cp(),  # DNS smoke: apply
            _cp(stdout="Running"),  # DNS smoke: pod status
            _cp(),  # DNS smoke: cleanup
        ]
        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_cluster_list_parse_error_fails_gracefully(self) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout="not-json")

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_dns_smoke_http_error_treated_as_unreachable(self) -> None:
        import urllib.error as _ue

        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch("hallm.cli.subcommands.k8s.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                side_effect=_ue.HTTPError("http://x", 500, "boom", {}, None),  # type: ignore[arg-type]
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# get-cert
# ---------------------------------------------------------------------------


class TestGetCert:
    def test_get_cert_success(self, tmp_path: Path) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch(
                "subprocess.run",
                side_effect=[_cp(stdout=_CERT_B64), _cp(stdout=_KEY_B64)],
            ),
            patch.object(settings, "SECRETS_PATH", sd),
        ):
            result = runner.invoke(app, ["get-cert"])

        assert result.exit_code == 0
        assert "Cert →" in result.output
        assert "Key  →" in result.output
        assert "BEGIN CERTIFICATE" in (sd / "cerberus-ca.pem").read_text()
        assert "BEGIN EC PRIVATE KEY" in (sd / "cerberus-ca.key").read_text()

    def test_get_cert_kubectl_fails(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="not found")):
            result = runner.invoke(app, ["get-cert"])
        assert result.exit_code == 1
        assert "cerberus-ca-secret" in result.output

    def test_get_cert_empty_cert(self, tmp_path: Path) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch("subprocess.run", return_value=_cp(returncode=0, stdout="")),
            patch.object(settings, "SECRETS_PATH", sd),
        ):
            result = runner.invoke(app, ["get-cert"])
        assert result.exit_code == 1
        assert "empty" in result.output

    def test_get_cert_empty_key(self, tmp_path: Path) -> None:
        sd = tmp_path / ".hallm"
        sd.mkdir()
        with (
            patch("subprocess.run", side_effect=[_cp(stdout=_CERT_B64), _cp(stdout="")]),
            patch.object(settings, "SECRETS_PATH", sd),
        ):
            result = runner.invoke(app, ["get-cert"])
        assert result.exit_code == 1
        assert "empty" in result.output


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_passes_when_all_checks_succeed(self) -> None:
        with patch(
            "hallm.cli.subcommands.k8s._PREFLIGHT_CHECKS",
            (("dummy", lambda: (True, None)),),
        ):
            result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 0
        assert "All preflight checks passed" in result.output

    def test_fails_when_any_check_fails(self) -> None:
        with patch(
            "hallm.cli.subcommands.k8s._PREFLIGHT_CHECKS",
            (("dummy", lambda: (False, "do this thing")),),
        ):
            result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 1
        assert "do this thing" in result.output


# ---------------------------------------------------------------------------
# sync-secrets
# ---------------------------------------------------------------------------


class TestSyncSecrets:
    def test_no_env_files(self, secrets_dir: Path) -> None:
        result = runner.invoke(app, ["sync-secrets"])
        assert result.exit_code == 0
        assert "No .env files found" in result.output

    def test_creates_secrets_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "new-hallm"
        monkeypatch.setattr(settings, "SECRETS_PATH", missing)
        result = runner.invoke(app, ["sync-secrets"])

        assert missing.exists()
        assert result.exit_code == 0

    def test_named_secret_kubectl_create_fails(self, secrets_dir: Path) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="auth error")):
            result = runner.invoke(app, ["sync-secrets"])

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
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 1
        assert "kubectl apply" in result.output

    def test_named_secret_success(self, secrets_dir: Path) -> None:
        (secrets_dir / "myapp.env").write_text("KEY=val\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 0
        assert "myapp.env → Secret 'myapp'" in result.output
        assert "Done" in result.output

    def test_dotenv_maps_to_hallm_env(self, secrets_dir: Path) -> None:
        (secrets_dir / ".env").write_text("FOO=bar\n")
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="yaml: content"), _cp()],
        ):
            result = runner.invoke(app, ["sync-secrets"])

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
            result = runner.invoke(app, ["sync-secrets"])

        assert result.exit_code == 0
        assert "alpha.env → Secret 'alpha'" in result.output
        assert "beta.env → Secret 'beta'" in result.output
        assert ".env → Secret 'hallm-env'" in result.output


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_missing_manifest_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = tmp_path / "k8s"
        empty.mkdir()
        monkeypatch.setattr(settings, "K8S_PATH", empty)
        monkeypatch.setattr(settings, "ROOT_PATH", tmp_path)

        result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "No manifest found" in result.output

    def test_success_no_label_resources(self, k8s_dir: Path) -> None:
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

    def test_success_with_label_resources(self, k8s_dir: Path) -> None:
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

    def test_confirmation_abort(self, k8s_dir: Path) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5,
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="n\n")

        assert result.exit_code != 0

    def test_confirmation_proceed(self, k8s_dir: Path) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5 + [_cp()],
        ):
            result = runner.invoke(app, ["remove", "ollama"], input="y\n")

        assert result.exit_code == 0

    def test_manifest_delete_fails(self, k8s_dir: Path) -> None:
        with patch(
            "subprocess.run",
            side_effect=[_cp(stdout="")] * 5 + [_cp(returncode=1, stderr="delete err")],
        ):
            result = runner.invoke(app, ["remove", "ollama", "--yes"])

        assert result.exit_code == 1
        assert "Failed to delete" in result.output

    def test_custom_namespace(self, k8s_dir: Path) -> None:
        with patch("subprocess.run", side_effect=[_cp(stdout="")] * 5 + [_cp()]) as mock:
            result = runner.invoke(app, ["remove", "ollama", "--yes", "--namespace", "ollama"])

        assert result.exit_code == 0
        preview_args = mock.call_args_list[0][0][0]
        assert "ollama" in preview_args


# ---------------------------------------------------------------------------
# seed-heimdall
# ---------------------------------------------------------------------------


class TestSeedHeimdall:
    def test_no_pod_fails(self) -> None:
        with patch("subprocess.run", return_value=_cp(stdout="")):
            result = runner.invoke(app, ["seed-heimdall"])
        assert result.exit_code == 1
        assert "No Heimdall pod" in result.output

    def test_db_not_ready_within_timeout(self) -> None:
        # 1 call to find pod, then poll loop returns False forever.
        with (
            patch(
                "subprocess.run",
                side_effect=[_cp(stdout="heimdall-0")] + [_cp(returncode=1)] * 100,
            ),
            patch("hallm.cli.base.poll.time.monotonic", side_effect=[0, 0, 200, 200]),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["seed-heimdall", "--timeout", "1"])
        assert result.exit_code == 1
        assert "did not appear" in result.output

    def test_seed_success(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(stdout="heimdall-0"),  # find pod
                    _cp(returncode=0, stdout="items"),  # db ready probe
                    _cp(),  # sqlite3 seed
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["seed-heimdall"])
        assert result.exit_code == 0
        assert "Seeded" in result.output

    def test_sqlite_seed_fails(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(stdout="heimdall-0"),
                    _cp(returncode=0, stdout="items"),
                    _cp(returncode=1, stderr="locked"),
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["seed-heimdall"])
        assert result.exit_code == 1
        assert "sqlite3 seed failed" in result.output
