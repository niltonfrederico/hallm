"""Unit tests for hallm.core.settings."""

import pytest

# Settings has class-level attributes for env-driven values with defaults.
# Database connection bits use @cached_property so each instance re-reads env
# on first access — that lets tests monkeypatch DATABASE_* and instantiate fresh.

_REQUIRED_ENV: dict[str, str] = {
    "DATABASE_DRIVER": "postgresql",
    "POSTGRES_USER": "testuser",
    "POSTGRES_PASSWORD": "testpass",
    "POSTGRES_DB": "testdb",
    "DATABASE_LOCAL_HOST": "localhost",
    "DATABASE_PROD_HOST": "prod.db.example.com",
}


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, val in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------


class TestPathConstants:
    def test_root_path_exists(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.ROOT_PATH.exists()

    def test_k8s_path_is_under_root(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.K8S_PATH == Settings.ROOT_PATH / "k8s"

    def test_project_path_is_under_root(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.PROJECT_PATH == Settings.ROOT_PATH / "hallm"

    def test_cli_path_is_under_project(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.CLI_PATH == Settings.PROJECT_PATH / "cli"

    def test_secrets_path_is_under_home(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.SECRETS_PATH.name == ".hallm"


# ---------------------------------------------------------------------------
# database / database_url / tortoise_database_url
# ---------------------------------------------------------------------------


class TestDatabase:
    def test_database_dict_has_required_keys(self, base_env: None) -> None:
        from hallm.core.settings import Settings

        s = Settings()
        assert s.database["user"] == "testuser"
        assert s.database["password"] == "testpass"
        assert s.database["name"] == "testdb"

    def test_database_url_localhost(self, base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "localhost")
        from hallm.core.settings import Settings

        s = Settings()
        # Class attribute is set at import time; override on instance.
        s.environment = "localhost"
        assert "localhost" in s.database_url
        assert "prod.db.example.com" not in s.database_url

    def test_database_url_production(self, base_env: None) -> None:
        from hallm.core.settings import Settings

        s = Settings()
        s.environment = "production"
        assert "prod.db.example.com" in s.database_url
        assert "localhost" not in s.database_url

    def test_tortoise_database_url_has_asyncpg_driver(self, base_env: None) -> None:
        from hallm.core.settings import Settings

        s = Settings()
        s.environment = "localhost"
        assert "+asyncpg" in s.tortoise_database_url
        assert s.tortoise_database_url.startswith("postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# Class-level defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_rustfs_bucket_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.rustfs_bucket == "hallm"

    def test_rustfs_region_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.rustfs_region == "us-east-1"

    def test_docker_context_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.DOCKER_CONTEXT == "hallm"

    def test_environment_default_is_localhost(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.environment == "localhost"

    def test_debug_default_is_false(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.debug is False

    def test_otel_service_name_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.otel_service_name == "hallm"

    def test_gotify_url_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.gotify_url == "https://gotify.hallm.local"

    def test_paperless_url_default(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.paperless_url == "https://paperless.hallm.local"
