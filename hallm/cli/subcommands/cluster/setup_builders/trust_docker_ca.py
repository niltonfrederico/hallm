"""Trust the Cerberus CA in the host Docker daemon's per-registry certs.d."""

from typing import ClassVar

from hallm.cli.subcommands import secrets as _secrets
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import settings


class TrustDockerCaStep(Step):
    name: ClassVar[str] = "Trusting Cerberus CA for Docker registry"

    def run(self) -> None:
        pem_path = settings.SECRETS_PATH / "cerberus-ca.pem"
        _secrets._configure_docker_registry_cert(pem_path)
