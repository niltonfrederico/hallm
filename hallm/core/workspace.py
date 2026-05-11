"""Repo workspace discovery.

Locates the active hallm checkout when commands need to resolve repo-relative
paths (k8s manifests, Dockerfiles, network configs). The CLI ships installed
globally via ``uv tool install --editable``, but workspace-bound commands need
to know *which* checkout to use; discovery makes that explicit and overridable.
"""

import os
import tomllib
from pathlib import Path

import typer

_MARKER_FILE = "pyproject.toml"
_HALLM_REPO_ENV = "HALLM_REPO"
_REPO_POINTER = Path.home() / ".hallm" / "repo"


class RepoNotFound(Exception):
    """Raised when a workspace-bound command runs without a discoverable repo."""


def _is_hallm_checkout(path: Path) -> bool:
    pyproject = path / _MARKER_FILE
    if not pyproject.is_file():
        return False
    try:
        data = tomllib.loads(pyproject.read_text())
    except OSError, tomllib.TOMLDecodeError:
        return False
    return data.get("project", {}).get("name") == "hallm"


def _from_env() -> Path | None:
    value = os.environ.get(_HALLM_REPO_ENV)
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if _is_hallm_checkout(candidate) else None


def _from_walk_up() -> Path | None:
    current = Path.cwd().resolve()
    for parent in (current, *current.parents):
        if _is_hallm_checkout(parent):
            return parent
    return None


def _from_pointer() -> Path | None:
    if not _REPO_POINTER.exists():
        return None
    try:
        target = Path(_REPO_POINTER.read_text().strip()).expanduser()
    except OSError:
        return None
    return target if _is_hallm_checkout(target) else None


def find_repo() -> Path | None:
    """Resolve the active hallm repo root.

    Order: ``$HALLM_REPO`` env var, walk-up from cwd, ``~/.hallm/repo`` pointer.
    Returns ``None`` if no valid checkout is discoverable so callers can decide
    whether to degrade or fail. Re-resolved on every call — Settings memoises
    the result via ``@cached_property`` for the lifetime of one CLI invocation.
    """
    for source in (_from_env, _from_walk_up, _from_pointer):
        if (found := source()) is not None:
            return found
    return None


def require_repo() -> Path:
    """Return the active hallm repo, exiting the CLI with a helpful message if absent."""
    repo = find_repo()
    if repo is None:
        typer.echo(
            "Error: no hallm checkout found.\n"
            "  - Set HALLM_REPO to the checkout path, or\n"
            "  - cd into a hallm checkout, or\n"
            f"  - write the path into {_REPO_POINTER} "
            "(automatic when you run `hallm install`).",
            err=True,
        )
        raise typer.Exit(code=1)
    return repo
