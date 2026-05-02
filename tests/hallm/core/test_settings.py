"""Unit tests for hallm.core.settings."""

import pytest

from hallm.core.settings import Settings

# Settings has class-level attributes for env-driven values with defaults.
# Database connection bits use @cached_property so each instance re-reads env
# on first access — that lets tests monkeypatch DATABASE_* and instantiate fresh.


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------


class TestPathConstants:
    def test_root_path_exists(self) -> None:
        assert Settings.ROOT_PATH.exists()

    @pytest.mark.parametrize(
        ("attr", "parent_attr", "suffix"),
        [
            ("K8S_PATH", "ROOT_PATH", "k8s"),
            ("PROJECT_PATH", "ROOT_PATH", "hallm"),
            ("CLI_PATH", "PROJECT_PATH", "cli"),
        ],
        ids=["k8s-under-root", "project-under-root", "cli-under-project"],
    )
    def test_path_constant_layout(self, attr: str, parent_attr: str, suffix: str) -> None:
        assert getattr(Settings, attr) == getattr(Settings, parent_attr) / suffix

    def test_secrets_path_is_under_home(self) -> None:
        assert Settings.SECRETS_PATH.name == ".hallm"


# ---------------------------------------------------------------------------
# database / database_url / tortoise_database_url
# ---------------------------------------------------------------------------


class TestDatabase:
    def test_database_dict_has_required_keys(self, base_env: None) -> None:
        s = Settings()
        assert s.database["user"] == "testuser"
        assert s.database["password"] == "testpass"
        assert s.database["name"] == "testdb"

    def test_database_url(self, base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "localhost")
        s = Settings()
        # Class attribute is set at import time; override on instance.
        s.environment = "localhost"
        assert "localhost" in s.database_url
        assert "prod.db.example.com" not in s.database_url

    def test_tortoise_database_url_has_asyncpg_driver(self, base_env: None) -> None:
        s = Settings()
        s.environment = "localhost"
        assert "+asyncpg" in s.tortoise_database_url
        assert s.tortoise_database_url.startswith("postgresql+asyncpg://")


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

    def test_otel_service_name_default(self) -> None:
        assert Settings.otel_service_name == "hallm"

    def test_gotify_url_default(self) -> None:
        assert Settings.gotify_url == "https://gotify.hallm.local"

    def test_paperless_url_default(self) -> None:
        assert Settings.paperless_url == "https://paperless.hallm.local"
