"""Unit tests for hallm.cli.subcommands.cluster."""

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.cluster import _setup_postgres
from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# File-local constants
# ---------------------------------------------------------------------------

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

_PATCH_MOUNT = patch("hallm.cli.subcommands.cluster._mount_storage")
_PATCH_PREFLIGHT = patch("hallm.cli.subcommands.cluster._run_preflight")
_PATCH_SETUP_POSTGRES = patch("hallm.cli.subcommands.cluster._setup_postgres")
_PATCH_DOCKER_CERT = patch("hallm.cli.subcommands.secrets._configure_docker_registry_cert")


def _socket_cm(*args: object, **kwargs: object) -> MagicMock:
    """Return a MagicMock that works as a context manager (open socket)."""
    return MagicMock()


def _healthcheck_happy_path_calls() -> list:
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


class TestSetup:
    def test_success(self, tmp_path: Path, runner: CliRunner, cert_b64: str) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp(stdout=cert_b64)) as mock,
            patch("hallm.cli.subcommands.cluster._manifest", return_value="cerberus: yaml"),
            patch("hallm.cli.subcommands.cluster._apply_all_service_manifests"),
            _PATCH_SETUP_POSTGRES,
            patch.object(settings, "SECRETS_PATH", secrets),
            _PATCH_DOCKER_CERT as mock_cert,
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "Done" in result.output
        assert "Syncing secrets" in result.output
        assert "SigNoz disabled" in result.output
        assert mock.call_count == 11
        mock_cert.assert_called_once_with(secrets / "cerberus-ca.pem")

    def test_k3d_create_fails(self, tmp_path: Path, runner: CliRunner) -> None:
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

    def test_api_server_not_ready(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp()),
            patch("hallm.cli.subcommands.cluster.poll_until", return_value=False),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "API server" in result.output

    def test_device_plugin_fails(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # k3d cluster create
                    _cp(),  # poll: kubectl get nodes
                    _cp(),  # ensure namespace docs
                    _cp(),  # apply traefik-config.yaml
                    _cp(returncode=1, stderr="dp fail"),  # apply ROCm device plugin
                    _cp(),  # k3d cluster delete cleanup
                ],
            ),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "kubectl apply failed" in result.output

    def test_cert_manager_fails(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # k3d cluster create
                    _cp(),  # poll: kubectl get nodes
                    _cp(),  # ensure namespace docs
                    _cp(),  # apply traefik-config.yaml
                    _cp(),  # apply ROCm device plugin
                    _cp(returncode=1),  # apply cert-manager
                    _cp(),  # k3d cluster delete cleanup
                ],
            ),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "cert-manager" in result.output

    def test_webhook_wait_fails(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # k3d cluster create
                    _cp(),  # poll: kubectl get nodes
                    _cp(),  # ensure namespace docs
                    _cp(),  # apply traefik-config.yaml
                    _cp(),  # apply ROCm device plugin
                    _cp(),  # apply cert-manager
                    _cp(returncode=1),  # wait for cert-manager-webhook
                    _cp(),  # k3d cluster delete cleanup
                ],
            ),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "webhook" in result.output

    def test_nuke_on_failure(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp()) as mock,
            patch("hallm.cli.subcommands.cluster.poll_until", return_value=False),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "nuking" in result.output
        last_cmd = mock.call_args_list[-1][0][0]
        assert "k3d" in last_cmd and "delete" in last_cmd

    def test_cerberus_apply_fails(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch(
                "subprocess.run",
                side_effect=[_cp()] * 7 + [_cp(returncode=1, stderr="cerb"), _cp()],
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="cerberus: yaml"),
            patch.object(settings, "SECRETS_PATH", secrets),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "Cerberus PKI" in result.output

    def test_context_override_is_applied(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        cert_b64: str,
    ) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        monkeypatch.setattr(settings, "DOCKER_CONTEXT", "hallm")
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp(stdout=cert_b64)),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="cerberus: yaml"),
            patch("hallm.cli.subcommands.cluster._apply_all_service_manifests"),
            _PATCH_SETUP_POSTGRES,
            patch.object(settings, "SECRETS_PATH", secrets),
            _PATCH_DOCKER_CERT,
        ):
            result = runner.invoke(app, ["setup", "--context", "default"])

        assert result.exit_code == 0
        assert "Docker context: default" in result.output
        assert settings.DOCKER_CONTEXT == "default"

    def test_cerberus_restored_from_existing_files(self, tmp_path: Path, runner: CliRunner) -> None:
        secrets = tmp_path / ".hallm"
        secrets.mkdir()
        (secrets / "cerberus-ca.pem").write_text("CERT")
        (secrets / "cerberus-ca.key").write_text("KEY")
        with (
            _PATCH_PREFLIGHT,
            _PATCH_MOUNT,
            patch("subprocess.run", return_value=_cp()) as mock,
            patch("hallm.cli.subcommands.cluster._apply_all_service_manifests"),
            _PATCH_SETUP_POSTGRES,
            patch.object(settings, "SECRETS_PATH", secrets),
            _PATCH_DOCKER_CERT as mock_cert,
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "Restoring" in result.output
        # k3d create + api-ready poll + ensure docs namespace + apply traefik-config
        # + apply ROCm + apply cert-manager + webhook wait + create-secret dry-run
        # + apply secret + apply issuer
        assert mock.call_count == 10
        mock_cert.assert_called_once_with(secrets / "cerberus-ca.pem")


# ---------------------------------------------------------------------------
# _setup_postgres
# ---------------------------------------------------------------------------


class TestSetupPostgres:
    def test_applies_manifest_waits_and_bootstraps(self, k8s_dir: Path) -> None:
        (k8s_dir / "postgres.yaml").write_text("apiVersion: v1")
        with (
            patch("subprocess.run", return_value=_cp()) as mock,
            patch("hallm.cli.subcommands.db._run_bootstrap"),
        ):
            _setup_postgres()

        # kubectl apply -f - (postgres manifest) + kubectl wait deploy/postgres
        assert mock.call_count == 2
        apply_cmd = mock.call_args_list[0][0][0]
        assert apply_cmd == ["kubectl", "apply", "-f", "-"]
        wait_cmd = mock.call_args_list[1][0][0]
        assert "deploy/postgres" in wait_cmd


# ---------------------------------------------------------------------------
# nuke
# ---------------------------------------------------------------------------


class TestNuke:
    def test_yes_flag_success(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 0
        assert "deleted" in result.output
        mock.assert_called_once()

    def test_yes_flag_delete_fails(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 1
        assert "delete failed" in result.output

    def test_confirmation_abort(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["nuke"], input="n\n")
        assert result.exit_code != 0

    def test_confirmation_proceed(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp()):
            result = runner.invoke(app, ["nuke"], input="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_volumes_flag_wipes_storage(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["nuke", "--yes", "--volumes"])

        assert result.exit_code == 0
        assert "deleted" in result.output
        assert mock.call_count == 2
        rm_args = mock.call_args_list[1][0][0]
        assert rm_args[:3] == ["sudo", "rm", "-rf"]

    def test_volumes_flag_included_in_confirmation_message(self, runner: CliRunner) -> None:
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

    def test_all_checks_pass(self, runner: CliRunner) -> None:
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_cluster_not_running_fails_exit(self, runner: CliRunner) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout=json.dumps([]))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_not_visible_fails_exit(self, runner: CliRunner) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[1] = _cp(stdout=json.dumps({"items": []}))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_port_not_reachable_fails_exit(self, runner: CliRunner) -> None:
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch(
                "hallm.cli.subcommands.cluster.socket.create_connection",
                side_effect=OSError("refused"),
            ),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_smoke_pod_apply_fails(self, runner: CliRunner) -> None:
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
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_cluster_list_parse_error_fails_gracefully(self, runner: CliRunner) -> None:
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout="not-json")

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_dns_smoke_http_error_treated_as_unreachable(self, runner: CliRunner) -> None:
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch("hallm.cli.subcommands.cluster.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.cluster.urllib.request.urlopen",
                side_effect=urllib.error.HTTPError("http://x", 500, "boom", {}, None),  # type: ignore[arg-type]
            ),
            patch("hallm.cli.subcommands.cluster._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_passes_when_all_checks_succeed(self, runner: CliRunner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster._preflight_checks",
            return_value=(("dummy", lambda: (True, None)),),
        ):
            result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 0
        assert "All preflight checks passed" in result.output

    def test_fails_when_any_check_fails(self, runner: CliRunner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster._preflight_checks",
            return_value=(("dummy", lambda: (False, "do this thing")),),
        ):
            result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 1
        assert "do this thing" in result.output


# ---------------------------------------------------------------------------
# diagnose
# ---------------------------------------------------------------------------

# Happy-path subprocess calls for diagnose (8 total):
#   0  docker info --format ...       (stream=True → stdout/stderr=None)
#   1  docker run alpine echo ok      (basic container)
#   2  docker run -p 80:80 ...        (port binding)
#   3  docker run --device /dev/kfd   (GPU device 1)
#   4  docker run --device /dev/dri/renderD128  (GPU device 2)
#   5  docker run -v /mnt/hallm ...   (storage mount)
#   6  k3d version                    (stream=True)
#   7  k3d cluster list               (stream=True)
_DIAGNOSE_ALL_OK = [_cp()] * 8


class TestDiagnose:
    def test_all_checks_pass(self, monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
        monkeypatch.setattr(
            "hallm.cli.subcommands.cluster._cgroup_memory_ok", lambda _uid: ("unlimited", True)
        )
        with patch("subprocess.run", side_effect=list(_DIAGNOSE_ALL_OK)):
            result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 0
        assert "All diagnostic checks passed" in result.output

    @pytest.mark.parametrize(
        ("call_index", "stderr", "expected_substring"),
        [
            (1, "permission denied", "permission denied"),
            (2, "port already in use", "[FAIL]"),
            (3, "no permission to /dev/kfd", "no permission to /dev/kfd"),
            (5, "mount denied", "mount denied"),
        ],
        ids=["basic-container", "port-bind", "gpu-device-mount", "storage-mount"],
    )
    def test_check_failure_modes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        call_index: int,
        stderr: str,
        expected_substring: str,
    ) -> None:
        monkeypatch.setattr(
            "hallm.cli.subcommands.cluster._cgroup_memory_ok", lambda _uid: ("unlimited", True)
        )
        calls = list(_DIAGNOSE_ALL_OK)
        calls[call_index] = _cp(returncode=1, stderr=stderr)
        with patch("subprocess.run", side_effect=calls):
            result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 1
        assert "[FAIL]" in result.output
        assert expected_substring in result.output

    def test_low_memory_cgroup_fails(
        self, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.setattr(
            "hallm.cli.subcommands.cluster._cgroup_memory_ok", lambda _uid: ("512 MB", False)
        )
        with patch("subprocess.run", side_effect=list(_DIAGNOSE_ALL_OK)):
            result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 1
        assert "[FAIL]" in result.output
        assert "512 MB" in result.output

    def test_context_override_applied(
        self, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.setattr(settings, "DOCKER_CONTEXT", "hallm")
        monkeypatch.setattr(
            "hallm.cli.subcommands.cluster._cgroup_memory_ok", lambda _uid: ("unlimited", True)
        )
        with patch("subprocess.run", side_effect=list(_DIAGNOSE_ALL_OK)):
            result = runner.invoke(app, ["diagnose", "--context", "default"])
        assert result.exit_code == 0
        assert "default" in result.output
