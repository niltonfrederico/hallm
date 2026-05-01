"""Application settings loaded from environment variables."""

from pathlib import Path

from environs import Env

env = Env()
env.read_env()


class Settings:
    # hallm/core/settings.py → hallm/core/ → hallm/ → repo root
    ROOT_PATH: Path = Path(__file__).parent.parent.parent
    PROJECT_PATH: Path = ROOT_PATH / "hallm"
    CLI_PATH: Path = PROJECT_PATH / "cli"
    K3D_PATH: Path = ROOT_PATH / "k3d"
    SECRETS_PATH: Path = Path.home() / ".hallm"

    # Local SSD used as persistent storage backing for the k3d cluster.
    # The device is mounted at STORAGE_MOUNT_PATH and bind-mounted into k3s nodes
    # so the local-path provisioner stores all PV data on the SSD.
    STORAGE_DEVICE: Path = Path("/dev/sda1")
    STORAGE_MOUNT_PATH: Path = Path("/mnt/hallm")

    environment: str = env.str("ENVIRONMENT", "localhost")
    debug: bool = env.bool("DEBUG", False)

    def __init__(self) -> None:
        self.database: dict[str, str] = {
            "driver": env.str("DATABASE_DRIVER"),
            "user": env.str("POSTGRES_USER"),
            "password": env.str("POSTGRES_PASSWORD"),
            "name": env.str("POSTGRES_DB"),
            "local_host": env.str("DATABASE_LOCAL_HOST"),
            "production_host": env.str("DATABASE_PROD_HOST"),
            "port": env.int("POSTGRES_PORT", 5432),
        }
        # RustFS (S3-compatible object storage)
        self.rustfs_endpoint: str = env.str(
            "RUSTFS_ENDPOINT",
            "http://rustfs.default.svc.cluster.local:9000",
        )
        self.rustfs_access_key: str = env.str("RUSTFS_ACCESS_KEY", "")
        self.rustfs_secret_key: str = env.str("RUSTFS_SECRET_KEY", "")
        self.rustfs_bucket: str = env.str("RUSTFS_BUCKET", "hallm")
        self.rustfs_region: str = env.str("RUSTFS_REGION", "us-east-1")
        self.rustfs_presign_expires: int = env.int("RUSTFS_PRESIGN_EXPIRES", 3600)

        # Valkey (shared Redis-compatible cache)
        self.valkey_url: str = env.str(
            "VALKEY_URL",
            "redis://valkey.default.svc.cluster.local:6379/0",
        )

        # Gotify (push notifications)
        self.gotify_url: str = env.str("GOTIFY_URL", "https://gotify.hallm.local")
        self.gotify_app_token: str = env.str("GOTIFY_APP_TOKEN", "")

        # Paperless-ngx (document management)
        self.paperless_url: str = env.str("PAPERLESS_URL", "https://paperless.hallm.local")
        self.paperless_token: str = env.str("PAPERLESS_TOKEN", "")

        # Glitchtip (Sentry-compatible error tracking)
        self.glitchtip_dsn: str = env.str("GLITCHTIP_DSN", "")

        # SigNoz / OpenTelemetry
        self.otel_endpoint: str = env.str(
            "OTEL_ENDPOINT",
            "http://signoz-otel-collector.signoz.svc.cluster.local:4317",
        )
        self.otel_service_name: str = env.str("OTEL_SERVICE_NAME", "hallm")

        # Spotify API (your_spotify)
        self.spotify_client_id: str = env.str("SPOTIFY_CLIENT_ID", "")
        self.spotify_client_secret: str = env.str("SPOTIFY_CLIENT_SECRET", "")

    def _build_database_url(self, driver: str | None = None) -> str:
        db_driver = self.database["driver"]
        if driver:
            db_driver += f"+{driver}"

        user = self.database["user"]
        password = self.database["password"]
        name = self.database["name"]
        port = self.database["port"]

        host = (
            self.database["local_host"]
            if self.environment == "localhost"
            else self.database["production_host"]
        )

        return f"{db_driver}://{user}:{password}@{host}:{port}/{name}"

    @property
    def database_url(self) -> str:
        """Construct the database URL for localhost from the individual components."""
        return self._build_database_url()

    @property
    def tortoise_database_url(self) -> str:
        """Construct the database URL for Tortoise ORM, which requires a driver prefix."""
        return self._build_database_url("asyncpg")


settings = Settings()
