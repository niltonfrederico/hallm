"""Create the k3d cluster with rootless Docker, GPU mounts, and host storage."""

from typing import ClassVar

from hallm.cli.base import docker as _docker
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


class CreateClusterStep(Step):
    name: ClassVar[str] = "Creating k3d cluster (first run may take ~10 min)"

    def is_satisfied(self) -> bool:
        result = _docker.run(["k3d", "cluster", "list", ClusterSettings.NAME, "--no-headers"])
        return result.returncode == 0 and ClusterSettings.NAME in result.stdout

    def run(self) -> None:
        _docker.run_or_fail(
            [
                "k3d",
                "cluster",
                "create",
                ClusterSettings.NAME,
                "--volume",
                "/dev/kfd:/dev/kfd@all",
                "--volume",
                "/dev/dri:/dev/dri@all",
                "--volume",
                f"{settings.STORAGE_MOUNT_PATH}:/var/lib/rancher/k3s/storage@all",
                "--volume",
                f"{settings.SHARED_VOLUMES_PATH}:{settings.SHARED_VOLUMES_NODE_PATH}@all",
                "--volume",
                f"{settings.CONFIG_VOLUMES_PATH}:{settings.CONFIG_VOLUMES_NODE_PATH}@all",
                "-p",
                "80:80@loadbalancer",
                "-p",
                "443:443@loadbalancer",
                "-p",
                "10432:5432@loadbalancer",
                "-p",
                "10300:5000@loadbalancer",
                "-p",
                "10379:6379@loadbalancer",
                "--registry-config",
                str(settings.k8s_path / "registries.yaml"),
                "--k3s-arg",
                "--kubelet-arg=feature-gates=KubeletInUserNamespace=true@server:*",
                # Disable kube-router's network policy controller. We run zero
                # NetworkPolicies, and on the nf_tables backend its periodic
                # full iptables-restore of the per-pod KUBE-POD-FW chains grows
                # past the netlink socket buffer ("sendmsg: Message too large"),
                # aborting mid-sync and leaving the filter table incomplete —
                # which silently black-holes NEW flows to ClusterIPs while
                # ESTABLISHED ones survive (old pods fine, new pods can't reach
                # Services/DNS). Dropping it removes the failure mode entirely.
                "--k3s-arg",
                "--disable-network-policy@server:*",
                "--timeout",
                "15m0s",
            ],
            "k3d cluster create failed",
            stream=True,
        )
