"""Application settings loaded from environment variables."""

from functools import cached_property
from pathlib import Path

from environs import Env

env = Env()
env.read_env()


class Settings:
    """Project-wide configuration.

    Attributes with sensible defaults are read from the environment at class
    definition time (single source of truth, evaluated once at import). The
    database connection bits have no defaults and are read on first access via
    :class:`functools.cached_property`, so each :class:`Settings` instance can
    pick up monkeypatched env vars in tests.
    """

    # ------------------------------------------------------------------
    # Paths (derived from this file's location)
    # ------------------------------------------------------------------
    # hallm/core/settings.py → hallm/core/ → hallm/ → repo root
    ROOT_PATH: Path = Path(__file__).parent.parent.parent
    PROJECT_PATH: Path = ROOT_PATH / "hallm"
    CLI_PATH: Path = PROJECT_PATH / "cli"
    K8S_PATH: Path = ROOT_PATH / "k8s"
    SECRETS_PATH: Path = Path.home() / ".hallm"

    # Local SSD used as persistent storage backing for the k3d cluster.
    # The device is mounted at STORAGE_MOUNT_PATH and bind-mounted into k3s nodes
    # so the local-path provisioner stores all PV data on the SSD.
    STORAGE_DEVICE: Path = Path("/dev/sda1")
    STORAGE_MOUNT_PATH: Path = Path("/mnt/hallm")

    # ------------------------------------------------------------------
    # Environment-driven (all have defaults so module import never fails)
    # ------------------------------------------------------------------
    # Docker context that hosts the k3d cluster. Points at a rootless Docker
    # daemon so the user's default daemon can be wiped/managed independently.
    DOCKER_CONTEXT: str = env.str("HALLM_DOCKER_CONTEXT", "hallm")

    environment: str = env.str("ENVIRONMENT", "localhost")
    debug: bool = env.bool("DEBUG", False)

    # RustFS (S3-compatible object storage)
    rustfs_endpoint: str = env.str(
        "RUSTFS_ENDPOINT", "http://rustfs.default.svc.cluster.local:9000"
    )
    rustfs_access_key: str = env.str("RUSTFS_ACCESS_KEY", "")
    rustfs_secret_key: str = env.str("RUSTFS_SECRET_KEY", "")
    rustfs_bucket: str = env.str("RUSTFS_BUCKET", "hallm")
    rustfs_region: str = env.str("RUSTFS_REGION", "us-east-1")
    rustfs_presign_expires: int = env.int("RUSTFS_PRESIGN_EXPIRES", 3600)

    # Valkey (shared Redis-compatible cache)
    valkey_url: str = env.str("VALKEY_URL", "redis://valkey.default.svc.cluster.local:6379/0")

    # Gotify (push notifications)
    gotify_url: str = env.str("GOTIFY_URL", "https://gotify.hallm.local")
    gotify_app_token: str = env.str("GOTIFY_APP_TOKEN", "")

    # Paperless-ngx (document management)
    paperless_url: str = env.str("PAPERLESS_URL", "https://paperless.hallm.local")
    paperless_token: str = env.str("PAPERLESS_TOKEN", "")

    # Glitchtip (Sentry-compatible error tracking)
    glitchtip_dsn: str = env.str("GLITCHTIP_DSN", "")

    # SigNoz / OpenTelemetry
    otel_endpoint: str = env.str(
        "OTEL_ENDPOINT", "http://signoz-otel-collector.signoz.svc.cluster.local:4317"
    )
    otel_service_name: str = env.str("OTEL_SERVICE_NAME", "hallm")

    # Spotify API (your_spotify)
    spotify_client_id: str = env.str("SPOTIFY_CLIENT_ID", "")
    spotify_client_secret: str = env.str("SPOTIFY_CLIENT_SECRET", "")

    # ------------------------------------------------------------------
    # Database (no defaults — read lazily so tests can monkeypatch env)
    # ------------------------------------------------------------------
    @cached_property
    def database(self) -> dict[str, str | int]:
        return {
            "driver": env.str("DATABASE_DRIVER"),
            "user": env.str("POSTGRES_USER"),
            "password": env.str("POSTGRES_PASSWORD"),
            "name": env.str("POSTGRES_DB"),
            "local_host": env.str("DATABASE_LOCAL_HOST"),
            "production_host": env.str("DATABASE_PROD_HOST"),
            "port": env.int("POSTGRES_PORT", 5432),
        }

    def _build_database_url(self, driver: str | None = None) -> str:
        db = self.database
        db_driver = str(db["driver"])
        if driver:
            db_driver += f"+{driver}"

        host = db["local_host"] if self.environment == "localhost" else db["production_host"]
        return f"{db_driver}://{db['user']}:{db['password']}@{host}:{db['port']}/{db['name']}"

    @cached_property
    def database_url(self) -> str:
        """Construct the database URL from the individual components."""
        return self._build_database_url()

    @cached_property
    def tortoise_database_url(self) -> str:
        """Construct the database URL for Tortoise ORM, which requires a driver prefix."""
        return self._build_database_url("asyncpg")


settings = Settings()
