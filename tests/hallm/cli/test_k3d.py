"""Unit tests for the k3d CLI subcommand."""

import json
import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

from typer.testing import CliRunner

from hallm.cli.subcommands.k3d import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


def _socket_cm(*args, **kwargs) -> MagicMock:
    """Return a MagicMock that works as a context manager (open socket)."""
    return MagicMock()


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
# setup() makes 5 subprocess.run calls:
#   1. k3d cluster create
#   2. kubectl apply device plugin
#   3. kubectl apply cert-manager
#   4. kubectl wait cert-manager webhook
#   5. kubectl apply cerberus (direct subprocess.run, reads cerberus.yaml)


class TestSetup:
    def test_success(self):
        with (
            patch("subprocess.run", return_value=_cp()) as mock,
            patch("hallm.cli.subcommands.k3d._manifest", return_value="cerberus: yaml"),
            patch("hallm.cli.subcommands.k3d._install_signoz"),
            patch("hallm.cli.subcommands.k3d._apply_all_service_manifests"),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "Done" in result.output
        assert mock.call_count == 5

    def test_k3d_create_fails(self):
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="boom")):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "k3d cluster create failed" in result.output

    def test_device_plugin_fails(self):
        with patch("subprocess.run", side_effect=[_cp(), _cp(returncode=1, stderr="dp fail")]):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "kubectl apply failed" in result.output

    def test_cert_manager_fails(self):
        with patch("subprocess.run", side_effect=[_cp(), _cp(), _cp(returncode=1)]):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "cert-manager" in result.output

    def test_webhook_wait_fails(self):
        with patch("subprocess.run", side_effect=[_cp(), _cp(), _cp(), _cp(returncode=1)]):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "webhook" in result.output

    def test_cerberus_apply_fails(self):
        with (
            patch(
                "subprocess.run",
                side_effect=[_cp()] * 4 + [_cp(returncode=1, stderr="cerb")],
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="cerberus: yaml"),
        ):
            result = runner.invoke(app, ["setup"])

        assert result.exit_code == 1
        assert "Cerberus PKI" in result.output


# ---------------------------------------------------------------------------
# nuke
# ---------------------------------------------------------------------------


class TestNuke:
    def test_yes_flag_success(self):
        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 0
        assert "deleted" in result.output
        mock.assert_called_once()

    def test_yes_flag_delete_fails(self):
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="err")):
            result = runner.invoke(app, ["nuke", "--yes"])

        assert result.exit_code == 1
        assert "delete failed" in result.output

    def test_confirmation_abort(self):
        result = runner.invoke(app, ["nuke"], input="n\n")
        assert result.exit_code != 0

    def test_confirmation_proceed(self):
        with patch("subprocess.run", return_value=_cp()):
            result = runner.invoke(app, ["nuke"], input="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.output


# ---------------------------------------------------------------------------
# healthcheck
# ---------------------------------------------------------------------------


class TestHealthcheck:
    def _urlopen_ok(self) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=MagicMock(status=200))
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_all_checks_pass(self):
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch("hallm.cli.subcommands.k3d.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_cluster_not_running_fails_exit(self):
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout=json.dumps([]))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k3d.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_not_visible_fails_exit(self):
        calls = _healthcheck_happy_path_calls()
        calls[1] = _cp(stdout=json.dumps({"items": []}))

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k3d.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_port_not_reachable_fails_exit(self):
        with (
            patch("subprocess.run", side_effect=_healthcheck_happy_path_calls()),
            patch(
                "hallm.cli.subcommands.k3d.socket.create_connection",
                side_effect=OSError("refused"),
            ),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_gpu_smoke_pod_apply_fails(self):
        # When GPU smoke apply fails it returns early; DNS smoke still runs.
        calls = [
            _cp(stdout=_CLUSTER_LIST_OK),  # cluster list
            _cp(stdout=_NODES_OK),  # get node
            _cp(stdout=_DS_OK),  # get ds
            _cp(stdout=_ISSUER_OK),  # get clusterissuer
            _cp(returncode=1, stderr="apply fail"),  # GPU smoke apply fails
            _cp(),  # DNS smoke: apply
            _cp(stdout="Running"),  # DNS smoke: pod status
            _cp(),  # DNS smoke: cleanup
        ]
        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k3d.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_cluster_list_parse_error_fails_gracefully(self):
        calls = _healthcheck_happy_path_calls()
        calls[0] = _cp(stdout="not-json")

        with (
            patch("subprocess.run", side_effect=calls),
            patch("hallm.cli.subcommands.k3d.socket.create_connection", side_effect=_socket_cm),
            patch(
                "hallm.cli.subcommands.k3d.urllib.request.urlopen",
                return_value=self._urlopen_ok(),
            ),
            patch("hallm.cli.subcommands.k3d._manifest", return_value="smoke: yaml"),
            patch("hallm.cli.subcommands.k3d.time.monotonic", return_value=0),
            patch("hallm.cli.subcommands.k3d.time.sleep"),
        ):
            result = runner.invoke(app, ["healthcheck"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output
