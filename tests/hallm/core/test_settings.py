"""Unit tests for hallm.core.settings."""

from pathlib import Path

import pytest

from hallm.core import workspace
from hallm.core.settings import Settings

# Settings has class-level attributes for env-driven values with defaults.
# Database connection bits use @cached_property so each instance re-reads env
# on first access — that lets tests monkeypatch DATABASE_* and instantiate fresh.


# ---------------------------------------------------------------------------
# Package-relative path constants (always valid, no repo needed)
# ---------------------------------------------------------------------------


class TestPackagePaths:
    def test_project_path_points_at_hallm_package(self) -> None:
        assert Settings.PROJECT_PATH.name == "hallm"
        assert (Settings.PROJECT_PATH / "core" / "settings.py").exists()

    def test_cli_path_is_under_project(self) -> None:
        assert Settings.CLI_PATH == Settings.PROJECT_PATH / "cli"

    def test_secrets_path_is_under_home(self) -> None:
        assert Settings.SECRETS_PATH.name == ".hallm"


# ---------------------------------------------------------------------------
# Repo-bound paths (lazy, resolved via workspace.require_repo)
# ---------------------------------------------------------------------------


class TestRepoPaths:
    def test_repo_root_resolves_via_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(workspace, "find_repo", lambda: tmp_path)
        s = Settings()
        assert s.repo_root == tmp_path
        assert s.k8s_path == tmp_path / "k8s"
        assert s.docker_path == tmp_path / "docker"
        assert s.network_path == tmp_path / "network"


# ---------------------------------------------------------------------------
# Class-level defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_rustfs_bucket_default(self) -> None:
        assert Settings.rustfs_bucket == "hallm"

    def test_rustfs_region_default(self) -> None:
        assert Settings.rustfs_region == "us-east-1"

    def test_docker_context_default(self) -> None:
        assert Settings.DOCKER_CONTEXT == "hallm"

    def test_environment_default_is_localhost(self) -> None:
        assert Settings.environment == "localhost"

    def test_debug_default_is_false(self) -> None:
        assert Settings.debug is False

    def test_gotify_url_default(self) -> None:
        assert Settings.gotify_url == "https://gotify.hallm.local"

    def test_paperless_url_default(self) -> None:
        assert Settings.paperless_url == "https://paperless.hallm.local"
