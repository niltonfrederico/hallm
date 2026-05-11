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

    # Feature flags for archived integrations.  Manifests for these services
    # live under k8s/archived/; flipping a flag back to True re-enables the
    # related Python wiring (CLI command registration, observability exporter,
    # HTTP client construction).  Move the manifest back to k8s/ to actually
    # deploy the service when re-enabling.
    signoz_enabled: bool = env.bool("SIGNOZ_ENABLED", False)
    glitchtip_enabled: bool = env.bool("GLITCHTIP_ENABLED", False)
    gotify_enabled: bool = env.bool("GOTIFY_ENABLED", False)

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
    paperless_db_password: str = env.str("PAPERLESS_DB_PASSWORD", "")

    # Glitchtip (Sentry-compatible error tracking)
    glitchtip_dsn: str = env.str("GLITCHTIP_DSN", "")
    glitchtip_db_password: str = env.str("GLITCHTIP_DB_PASSWORD", "")
    # Fraction of OTEL spans to forward to Glitchtip via SentrySpanProcessor.
    # 1.0 captures every span (fine on the dev cluster); lower in production.
    sentry_traces_sample_rate: float = env.float("SENTRY_TRACES_SAMPLE_RATE", 1.0)

    # SigNoz / OpenTelemetry
    otel_endpoint: str = env.str(
        "OTEL_ENDPOINT", "http://signoz-otel-collector.signoz.svc.cluster.local:4318"
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
            "host": env.str("DATABASE_HOST"),
            "port": env.int("POSTGRES_PORT", 5432),
        }

    def _build_database_url(self, driver: str | None = None) -> str:
        db = self.database
        db_driver = str(db["driver"])
        if driver:
            db_driver += f"+{driver}"

        host = db["host"]
        return f"{db_driver}://{db['user']}:{db['password']}@{host}:{db['port']}/{db['name']}"

    @cached_property
    def database_url(self) -> str:
        """Construct the database URL from the individual components."""
        return self._build_database_url()

    @cached_property
    def tortoise_database_url(self) -> str:
        """Construct the database URL for Tortoise ORM, which requires a driver prefix."""
        return self._build_database_url("asyncpg")


class ClusterSettings:
    """Constants for the hallm k3d cluster lifecycle.

    Accessed as class attributes (`ClusterSettings.NAME`); no singleton.
    All values are immutable knobs the setup pipeline reads — never overridden
    at runtime.
    """

    NAME: str = "hallm"
    DEFAULT_NAMESPACE: str = "default"
    UNREGISTRY_HOST: str = "unregistry.hallm.local"

    DEVICE_PLUGIN_URL: str = (
        "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
    )
    CERT_MANAGER_URL: str = (
        "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
    )

    # Base namespaces always created during setup, even if no Step declares them.
    # Step-declared namespaces (e.g. "signoz" from SignozStep) are unioned in
    # by build_setup_pipeline — they don't need to be listed here.
    REQUIRED_NAMESPACES: tuple[str, ...] = ("docs",)

    GPU_DEVICES: tuple[Path, ...] = (Path("/dev/kfd"), Path("/dev/dri/renderD128"))
    CGROUP_DELEGATE_FILE: Path = Path("/etc/systemd/system/user@.service.d/delegate.conf")
    REQUIRED_CGROUP_CONTROLLERS: frozenset[str] = frozenset({"cpu", "cpuset", "io"})


settings = Settings()
