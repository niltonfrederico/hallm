"""Container image build and push operations."""

from datetime import UTC
from datetime import datetime

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base.shell import fail as _fail
from hallm.core.settings import settings

app = typer.Typer(help="Container image operations.", no_args_is_help=True)

_REGISTRY = "unregistry.hallm.local"
_ORG = "hallm"


@app.command("publish")
def publish(
    name: str = typer.Argument(..., help="Image name to build and push (e.g. activitywatch)."),
) -> None:
    """Build, tag (latest + timestamp), push to unregistry, and prune local cache."""
    dockerfile = settings.ROOT_PATH / "docker" / f"Dockerfile.{name}"
    if not dockerfile.exists():
        _fail(f"Dockerfile not found: {dockerfile}")

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    base_tag = f"{_REGISTRY}/{_ORG}/{name}"
    tag_latest = f"{base_tag}:latest"
    tag_ts = f"{base_tag}:{timestamp}"

    typer.echo(f"==> Building {name} from {dockerfile.name}...")
    _docker.run_or_fail(
        [
            "docker",
            "build",
            "--tag",
            tag_latest,
            "--tag",
            tag_ts,
            "--file",
            str(dockerfile),
            str(settings.ROOT_PATH),
        ],
        f"Build failed for {name}",
    )

    for tag in (tag_latest, tag_ts):
        typer.echo(f"==> Pushing {tag}...")
        _docker.run_or_fail(["docker", "push", tag], f"Push failed for {tag}")

    typer.echo("==> Pruning local Docker build cache...")
    result = _docker.run(["docker", "buildx", "prune", "--force"])
    if result.returncode != 0:
        typer.echo(f"WARNING: cache prune failed: {result.stderr}", err=True)
    else:
        typer.echo(result.stdout.strip() or "  Cache cleared.")

    typer.echo(f"\n[OK]  {name} published as {tag_latest} and {tag_ts}")
