"""Targeted tests for the private helpers in hallm.cli.subcommands.k8s.

Most public commands are covered by test_k8s.py. This file exercises:

* the preflight checks individually
* _mount_storage branches
* _install_signoz / _apply_all_service_manifests
* the GPU/DNS smoke helpers
* _manifest
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import typer

from hallm.cli.subcommands import k8s as mod
from hallm.core.settings import settings


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# _manifest
# ---------------------------------------------------------------------------


class TestManifestHelper:
    def test_reads_file_under_k8s_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manifest = tmp_path / "ollama.yaml"
        manifest.write_text("kind: Namespace\n")
        monkeypatch.setattr(settings, "K8S_PATH", tmp_path)
        assert mod._manifest("ollama.yaml") == "kind: Namespace\n"

    def test_joins_subpath(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sub = tmp_path / "test"
        sub.mkdir()
        (sub / "smoke.yaml").write_text("smoke: yes\n")
        monkeypatch.setattr(settings, "K8S_PATH", tmp_path)
        assert mod._manifest("test", "smoke.yaml") == "smoke: yes\n"


# ---------------------------------------------------------------------------
# _mount_storage
# ---------------------------------------------------------------------------


class TestMountStorage:
    def test_already_mounted_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_DEVICE", Path("/dev/sda1"))
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/mnt/hallm"))
        with patch("subprocess.run", return_value=_cp(stdout="/mnt/hallm\n")) as mock:
            mod._mount_storage()
        assert mock.call_count == 1  # only findmnt

    def test_unmounts_then_mounts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_DEVICE", Path("/dev/sda1"))
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/mnt/hallm"))
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout="/mnt/wrong\n"),  # findmnt
                _cp(),  # umount
                _cp(),  # mkdir
                _cp(),  # mount
            ],
        ) as mock:
            mod._mount_storage()
        assert mock.call_count == 4

    def test_fresh_mount_when_unmounted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_DEVICE", Path("/dev/sda1"))
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/mnt/hallm"))
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(stdout=""),  # findmnt: not mounted
                _cp(),  # mkdir
                _cp(),  # mount
            ],
        ) as mock:
            mod._mount_storage()
        assert mock.call_count == 3


# ---------------------------------------------------------------------------
# Preflight check helpers
# ---------------------------------------------------------------------------


class TestPreflightChecks:
    def test_docker_context_ok(self) -> None:
        with patch("hallm.cli.subcommands.k8s._run", return_value=_cp()):
            ok, hint = mod._check_docker_context_exists()
        assert ok is True
        assert hint is None

    def test_docker_context_missing(self) -> None:
        with patch("hallm.cli.subcommands.k8s._run", return_value=_cp(returncode=1)):
            ok, hint = mod._check_docker_context_exists()
        assert ok is False
        assert "install-rootless-docker" in hint  # type: ignore[operator]

    def test_docker_daemon_reachable(self) -> None:
        with patch("hallm.cli.base.docker.run", return_value=_cp()):
            ok, _ = mod._check_docker_daemon_reachable()
        assert ok is True

    def test_docker_daemon_unreachable(self) -> None:
        with patch("hallm.cli.base.docker.run", return_value=_cp(returncode=1)):
            ok, hint = mod._check_docker_daemon_reachable()
        assert ok is False
        assert "systemctl" in hint  # type: ignore[operator]

    def test_unprivileged_ports_ok(self, tmp_path: Path) -> None:
        sysctl = tmp_path / "ports"
        sysctl.write_text("80\n")
        with patch.object(Path, "read_text", return_value="80"):
            ok, _ = mod._check_unprivileged_ports()
        assert ok is True

    def test_unprivileged_ports_too_high(self) -> None:
        with patch.object(Path, "read_text", return_value="1024"):
            ok, hint = mod._check_unprivileged_ports()
        assert ok is False
        assert "sysctl" in hint  # type: ignore[operator]

    def test_unprivileged_ports_unreadable(self) -> None:
        with patch.object(Path, "read_text", side_effect=OSError("perms")):
            ok, hint = mod._check_unprivileged_ports()
        assert ok is False
        assert "Could not read" in hint  # type: ignore[operator]

    def test_cgroup_delegation_missing_drop_in(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            ok, hint = mod._check_cgroup_delegation()
        assert ok is False
        assert "delegate.conf" in hint  # type: ignore[operator]

    def test_cgroup_delegation_unreadable_controllers(self) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", side_effect=OSError("nope")),
        ):
            ok, hint = mod._check_cgroup_delegation()
        assert ok is False
        assert "Could not read" in hint  # type: ignore[operator]

    def test_cgroup_delegation_missing_controllers(self) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="cpu memory"),
        ):
            ok, hint = mod._check_cgroup_delegation()
        assert ok is False
        assert "Missing" in hint  # type: ignore[operator]

    def test_cgroup_delegation_all_present(self) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="cpu cpuset io memory pids"),
        ):
            ok, _ = mod._check_cgroup_delegation()
        assert ok is True

    def test_gpu_devices_accessible(self) -> None:
        with patch("os.access", return_value=True):
            ok, _ = mod._check_gpu_devices()
        assert ok is True

    def test_gpu_devices_inaccessible(self) -> None:
        with patch("os.access", return_value=False):
            ok, hint = mod._check_gpu_devices()
        assert ok is False
        assert "render" in hint  # type: ignore[operator]

    def test_storage_owner_missing_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/no/such/path"))
        ok, hint = mod._check_storage_owner()
        assert ok is False
        assert "does not exist" in hint  # type: ignore[operator]

    def test_storage_owner_wrong_owner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", tmp_path)
        fake_stat = MagicMock()
        fake_stat.st_uid = 99999  # almost certainly not the test runner uid
        with patch.object(Path, "stat", return_value=fake_stat):
            ok, hint = mod._check_storage_owner()
        assert ok is False
        assert "chown" in hint  # type: ignore[operator]

    def test_storage_owner_correct(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", tmp_path)
        ok, _ = mod._check_storage_owner()
        assert ok is True


# ---------------------------------------------------------------------------
# _install_signoz
# ---------------------------------------------------------------------------


class TestInstallSignoz:
    def test_install_when_repo_missing(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # helm repo add (success)
                    _cp(),  # helm repo update
                    _cp(),  # kubectl create namespace
                    _cp(),  # helm upgrade --install
                    _cp(),  # kubectl apply ingress
                ],
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="ingress: yes"),
        ):
            mod._install_signoz()

    def test_install_repo_already_exists_is_not_fatal(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(returncode=1, stderr="repo already exists"),
                    _cp(),
                    _cp(),
                    _cp(),
                    _cp(),
                ],
            ),
            patch("hallm.cli.subcommands.k8s._manifest", return_value="ingress: yes"),
        ):
            mod._install_signoz()

    def test_install_repo_add_other_error_fails(self) -> None:
        with (
            patch("subprocess.run", return_value=_cp(returncode=1, stderr="permission denied")),
            pytest.raises(typer.Exit),
        ):
            mod._install_signoz()


# ---------------------------------------------------------------------------
# _apply_all_service_manifests
# ---------------------------------------------------------------------------


class TestApplyAllServiceManifests:
    def test_skips_managed_manifests(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("cerberus.yaml", "registries.yaml", "signoz-ingress.yaml", "ollama.yaml"):
            (tmp_path / name).write_text(f"kind: Test  # {name}")
        monkeypatch.setattr(settings, "K8S_PATH", tmp_path)
        with patch("hallm.cli.base.kubectl.apply") as apply:
            mod._apply_all_service_manifests()
        applied = [call.kwargs.get("label") for call in apply.call_args_list]
        assert applied == ["ollama"]


# ---------------------------------------------------------------------------
# Smoke test internals
# ---------------------------------------------------------------------------


class TestGpuSmoke:
    def test_apply_failure_returns_false(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="apply err")):
            assert mod._gpu_smoke_test() is False

    def test_pod_failed_phase_aborts(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # kubectl apply
                    _cp(stdout="Failed"),  # _pod_phase first poll → Failed
                    _cp(),  # delete
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            assert mod._gpu_smoke_test() is False


class TestStaticHealthCheckHelpers:
    def test_cluster_running_returncode_nonzero(self) -> None:
        with patch("hallm.cli.subcommands.k8s._docker.run", return_value=_cp(returncode=1)):
            assert mod._cluster_running_via_k3d() is False

    def test_cluster_running_invalid_json(self) -> None:
        with patch("hallm.cli.subcommands.k8s._docker.run", return_value=_cp(stdout="not-json")):
            assert mod._cluster_running_via_k3d() is False

    def test_gpu_visible_when_get_json_returns_none(self) -> None:
        with patch("hallm.cli.base.kubectl.get_json", return_value=None):
            assert mod._gpu_visible_to_kubernetes() is False

    def test_gpu_visible_swallows_typeerror(self) -> None:
        with patch(
            "hallm.cli.base.kubectl.get_json",
            return_value={"items": [{"status": {"allocatable": {"amd.com/gpu": object()}}}]},
        ):
            assert mod._gpu_visible_to_kubernetes() is False

    def test_amdgpu_daemonset_returns_false_when_get_json_none(self) -> None:
        with patch("hallm.cli.base.kubectl.get_json", return_value=None):
            assert mod._amdgpu_daemonset_ready() is False

    def test_amdgpu_daemonset_returns_false_when_no_amdgpu_ds(self) -> None:
        with patch(
            "hallm.cli.base.kubectl.get_json",
            return_value={"items": [{"metadata": {"name": "other-thing"}}]},
        ):
            assert mod._amdgpu_daemonset_ready() is False

    def test_cerberus_issuer_returns_false_when_get_json_none(self) -> None:
        with patch("hallm.cli.base.kubectl.get_json", return_value=None):
            assert mod._cerberus_issuer_ready() is False


class TestDnsSmoke:
    def test_apply_failure_returns_false(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(returncode=1, stderr="boom"),  # apply
                    _cp(),  # cleanup
                ],
            ),
        ):
            assert mod._dns_smoke_test() is False

    def test_pod_never_running_returns_false(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # apply
                    _cp(stdout="Pending"),  # poll attempt 1
                    _cp(),  # cleanup
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", side_effect=[0, 0, 100]),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            assert mod._dns_smoke_test() is False

    def test_http_unreachable_returns_false(self) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(),  # apply
                    _cp(stdout="Running"),  # poll attempt 1 (running)
                    _cp(),  # cleanup
                ],
            ),
            patch(
                "hallm.cli.subcommands.k8s.urllib.request.urlopen",
                side_effect=OSError("network down"),
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            assert mod._dns_smoke_test() is False
