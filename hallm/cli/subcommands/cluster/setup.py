"""Cluster setup command — composes Steps into the runnable pipeline."""

import typer

from hallm.cli.subcommands.cluster.setup_builders import Step
from hallm.cli.subcommands.cluster.setup_builders import build_setup_pipeline
from hallm.cli.subcommands.cluster.setup_builders.cerberus_pki import CerberusPkiStep
from hallm.cli.subcommands.cluster.setup_builders.cert_manager import CertManagerStep
from hallm.cli.subcommands.cluster.setup_builders.create_cluster import CreateClusterStep
from hallm.cli.subcommands.cluster.setup_builders.gotify import GotifyStep
from hallm.cli.subcommands.cluster.setup_builders.jupyter import JupyterStep
from hallm.cli.subcommands.cluster.setup_builders.memory_mcp import MemoryMcpStep
from hallm.cli.subcommands.cluster.setup_builders.mount_storage import MountStorageStep
from hallm.cli.subcommands.cluster.setup_builders.paperless import PaperlessStep
from hallm.cli.subcommands.cluster.setup_builders.postgres import PostgresStep
from hallm.cli.subcommands.cluster.setup_builders.preflight import PreflightStep
from hallm.cli.subcommands.cluster.setup_builders.rocm_plugin import ROCmPluginStep
from hallm.cli.subcommands.cluster.setup_builders.rustfs import RustfsStep
from hallm.cli.subcommands.cluster.setup_builders.shared_volumes import SharedVolumesStep
from hallm.cli.subcommands.cluster.setup_builders.signoz import SignozStep
from hallm.cli.subcommands.cluster.setup_builders.traefik_config import TraefikConfigStep
from hallm.cli.subcommands.cluster.setup_builders.trust_docker_ca import TrustDockerCaStep
from hallm.cli.subcommands.cluster.setup_builders.unregistry import UnregistryStep
from hallm.cli.subcommands.cluster.setup_builders.valkey import ValkeyStep
from hallm.cli.subcommands.cluster.setup_builders.wait_api import WaitApiStep
from hallm.core.settings import settings


def setup(
    context: str = typer.Option(
        settings.DOCKER_CONTEXT,
        "--context",
        help=(
            "Docker context for k3d/docker calls. "
            "Defaults to the rootless hallm context; pass 'default' to use the "
            "standard Docker daemon for debugging."
        ),
    ),
) -> None:
    """Create the hallm k3d cluster and apply every service manifest in k8s/."""
    if context != settings.DOCKER_CONTEXT:
        typer.echo(f"==> Docker context: {context}")
        settings.DOCKER_CONTEXT = context

    steps: list[Step] = [
        PreflightStep(),
        MountStorageStep(),
        CreateClusterStep(),
        WaitApiStep(),
        SharedVolumesStep(),
        TraefikConfigStep(),
        ROCmPluginStep(),
        CertManagerStep(),
        CerberusPkiStep(),
        TrustDockerCaStep(),
        UnregistryStep(),
        PostgresStep(),
        ValkeyStep(),
        RustfsStep(),
        PaperlessStep(),
        JupyterStep(),
        MemoryMcpStep(),
        GotifyStep(),
    ]
    if settings.signoz_enabled:
        steps.append(SignozStep())

    pipeline = build_setup_pipeline(steps)
    pipeline()

    typer.echo("\n==> Done. Cluster is ready.")
