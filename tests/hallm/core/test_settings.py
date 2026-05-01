"""Unit tests for hallm.core.settings."""

import pytest

# Never use the module-level `settings` singleton — always instantiate Settings() fresh
# so that monkeypatched env vars are picked up by environs at call-time.

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
# Path constants (class-level attrs — no env vars required)
# ---------------------------------------------------------------------------


class TestPathConstants:
    def test_root_path_exists(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.ROOT_PATH.exists()

    def test_k3d_path_is_under_root(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.K3D_PATH == Settings.ROOT_PATH / "k3d"

    def test_project_path_is_under_root(self) -> None:
        from hallm.core.settings import Settings

        assert Settings.PROJECT_PATH == Settings.ROOT_PATH / "hallm"


# ---------------------------------------------------------------------------
# database_url / tortoise_database_url
# ---------------------------------------------------------------------------


class TestDatabaseUrl:
    def test_database_url_localhost(self, base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "localhost")
        from hallm.core.settings import Settings

        s = Settings()
        assert "localhost" in s.database_url
        assert "prod.db.example.com" not in s.database_url

    def test_database_url_production(self, base_env: None) -> None:
        from hallm.core.settings import Settings

        s = Settings()
        s.environment = "production"  # class attr is set at import time; override on instance
        assert "prod.db.example.com" in s.database_url
        assert "localhost" not in s.database_url

    def test_tortoise_database_url_has_asyncpg_driver(self, base_env: None) -> None:
        from hallm.core.settings import Settings

        s = Settings()
        assert "+asyncpg" in s.tortoise_database_url
        assert s.tortoise_database_url.startswith("postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# RustFS defaults
# ---------------------------------------------------------------------------


class TestRustfsDefaults:
    def test_rustfs_bucket_default(self, base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RUSTFS_BUCKET", raising=False)
        from hallm.core.settings import Settings

        s = Settings()
        assert s.rustfs_bucket == "hallm"

    def test_rustfs_region_default(self, base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RUSTFS_REGION", raising=False)
        from hallm.core.settings import Settings

        s = Settings()
        assert s.rustfs_region == "us-east-1"
