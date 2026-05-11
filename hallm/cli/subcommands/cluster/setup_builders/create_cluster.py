"""Create the k3d cluster with rootless Docker, GPU mounts, and host storage."""

from typing import ClassVar

from hallm.cli.base import docker as _docker
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


class CreateClusterStep(Step):
    name: ClassVar[str] = "Creating k3d cluster (first run may take ~10 min)"

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
                str(settings.K8S_PATH / "registries.yaml"),
                "--k3s-arg",
                "--kubelet-arg=feature-gates=KubeletInUserNamespace=true@server:*",
                "--timeout",
                "15m0s",
            ],
            "k3d cluster create failed",
            stream=True,
        )
