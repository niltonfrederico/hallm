"""Tests for hallm.cli.subcommands.cluster.healthcheck."""

import socket
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

import hallm.cli.subcommands.cluster.healthcheck as hc
from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


class TestManifest:
    def test_joins_parts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sub = tmp_path / "test"
        sub.mkdir()
        (sub / "smoke.yaml").write_text("k: v\n")
        monkeypatch.setattr(settings, "K8S_PATH", tmp_path)
        assert hc._manifest("test", "smoke.yaml") == "k: v\n"


class TestClusterRunningViaK3d:
    def test_docker_failed(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck._docker.run",
            return_value=_cp(returncode=1),
        ):
            assert hc._cluster_running_via_k3d() is False

    def test_invalid_json(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck._docker.run",
            return_value=_cp(stdout="not-json"),
        ):
            assert hc._cluster_running_via_k3d() is False

    def test_no_match(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck._docker.run",
            return_value=_cp(stdout='[{"name":"other","serversRunning":1}]'),
        ):
            assert hc._cluster_running_via_k3d() is False

    def test_match(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck._docker.run",
            return_value=_cp(stdout='[{"name":"hallm","serversRunning":1}]'),
        ):
            assert hc._cluster_running_via_k3d() is True


class TestGpuVisibleToKubernetes:
    def test_not_a_dict(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=None,
        ):
            assert hc._gpu_visible_to_kubernetes() is False

    def test_no_items(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value={"items": []},
        ):
            assert hc._gpu_visible_to_kubernetes() is False

    def test_bad_allocatable(self) -> None:
        items = {"items": [{"status": {"allocatable": {"amd.com/gpu": object()}}}]}
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=items,
        ):
            assert hc._gpu_visible_to_kubernetes() is False

    def test_gpu_present(self) -> None:
        items = {"items": [{"status": {"allocatable": {"amd.com/gpu": "1"}}}]}
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=items,
        ):
            assert hc._gpu_visible_to_kubernetes() is True


class TestAmdgpuDaemonsetReady:
    def test_not_a_dict(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=None,
        ):
            assert hc._amdgpu_daemonset_ready() is False

    def test_no_amdgpu_ds(self) -> None:
        items = {"items": [{"metadata": {"name": "other-ds"}}]}
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=items,
        ):
            assert hc._amdgpu_daemonset_ready() is False

    def test_ready(self) -> None:
        items = {
            "items": [
                {
                    "metadata": {"name": "amdgpu-device-plugin"},
                    "status": {"desiredNumberScheduled": 1, "numberReady": 1},
                }
            ]
        }
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=items,
        ):
            assert hc._amdgpu_daemonset_ready() is True

    def test_not_ready(self) -> None:
        items = {
            "items": [
                {
                    "metadata": {"name": "amdgpu-device-plugin"},
                    "status": {"desiredNumberScheduled": 1, "numberReady": 0},
                }
            ]
        }
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=items,
        ):
            assert hc._amdgpu_daemonset_ready() is False


class TestCerberusIssuerReady:
    def test_not_a_dict(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value=None,
        ):
            assert hc._cerberus_issuer_ready() is False

    def test_ready(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value={"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ):
            assert hc._cerberus_issuer_ready() is True

    def test_not_ready(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.kubectl.get_json",
            return_value={"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        ):
            assert hc._cerberus_issuer_ready() is False


class TestPortReachable:
    def test_yes(self) -> None:
        class _Sock:
            def __enter__(self) -> _Sock:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.socket.create_connection",
            return_value=_Sock(),
        ):
            assert hc._port_reachable(80) is True

    def test_no(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.socket.create_connection",
            side_effect=OSError(),
        ):
            assert hc._port_reachable(80) is False


class TestPodPhase:
    def test_returns_stripped_phase(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
            return_value=_cp(stdout=" Running \n"),
        ):
            assert hc._pod_phase("p") == "Running"


class TestGpuSmokeTest:
    def _stub_manifest(self) -> str:
        return "kind: Pod\n"

    def test_apply_failure_short_circuits(self) -> None:
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(returncode=1, stderr="boom"),
            ),
        ):
            assert hc._gpu_smoke_test() is False

    def test_pod_succeeds(self) -> None:
        # Apply, then poll returns Succeeded immediately, then delete.
        calls = [
            _cp(),  # apply
            _cp(stdout="Succeeded"),  # phase poll
            _cp(),  # delete
        ]
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                side_effect=calls,
            ),
        ):
            assert hc._gpu_smoke_test() is True

    def test_pod_fails(self) -> None:
        calls = [
            _cp(),  # apply
            _cp(stdout="Failed"),  # phase poll → triggers _SmokeAborted
            _cp(),  # delete
        ]
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                side_effect=calls,
            ),
        ):
            assert hc._gpu_smoke_test() is False


class TestDnsSmokeTest:
    def test_apply_failure(self) -> None:
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(returncode=1, stderr="boom"),
            ),
        ):
            assert hc._dns_smoke_test() is False

    def test_pod_never_runs(self) -> None:
        # poll_until exits on timeout returning False
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(stdout="Pending"),
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.poll_until",
                return_value=False,
            ),
        ):
            assert hc._dns_smoke_test() is False

    def test_pod_running_http_ok(self) -> None:
        class _Resp:
            status = 200

            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(),
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.poll_until",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.urllib.request.urlopen",
                return_value=_Resp(),
            ),
        ):
            assert hc._dns_smoke_test() is True

    def test_http_error_under_400(self) -> None:
        err = urllib.error.HTTPError("http://x", 301, "moved", {}, None)  # type: ignore[arg-type]
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(),
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.poll_until",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.urllib.request.urlopen",
                side_effect=err,
            ),
        ):
            assert hc._dns_smoke_test() is True

    def test_oserror(self) -> None:
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._manifest",
                return_value="k:v",
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.subprocess.run",
                return_value=_cp(),
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.poll_until",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck.urllib.request.urlopen",
                side_effect=OSError("dns"),
            ),
        ):
            assert hc._dns_smoke_test() is False


class TestHealthcheckCommand:
    @pytest.fixture
    def _all_green(self):
        ctx = (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._cluster_running_via_k3d",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._gpu_visible_to_kubernetes",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._amdgpu_daemonset_ready",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._cerberus_issuer_ready",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._port_reachable",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._gpu_smoke_test",
                return_value=True,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._dns_smoke_test",
                return_value=True,
            ),
        )
        for c in ctx:
            c.start()
        yield
        for c in ctx:
            c.stop()

    def test_all_pass(self, runner, _all_green) -> None:
        result = runner.invoke(app, ["healthcheck"])
        assert result.exit_code == 0, result.output
        assert "All checks passed" in result.output

    def test_failure_exits(self, runner) -> None:
        with (
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._cluster_running_via_k3d",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._gpu_visible_to_kubernetes",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._amdgpu_daemonset_ready",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._cerberus_issuer_ready",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._port_reachable",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._gpu_smoke_test",
                return_value=False,
            ),
            patch(
                "hallm.cli.subcommands.cluster.healthcheck._dns_smoke_test",
                return_value=False,
            ),
        ):
            result = runner.invoke(app, ["healthcheck"])
        assert result.exit_code == 1
        assert "One or more checks failed" in result.output


def _unused() -> tuple[socket.socket, socket.socket]:
    # Keeps `socket` import warnings quiet (used only for typing above).
    raise NotImplementedError
