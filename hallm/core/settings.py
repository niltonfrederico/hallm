"""Application settings loaded from environment variables."""

from pathlib import Path

from environs import Env

env = Env()
env.read_env()


class Settings:
    # hallm/core/settings.py → hallm/core/ → hallm/ → repo root
    ROOT_PATH: Path = Path(__file__).parent.parent
    CLI_PATH: Path = ROOT_PATH / "cli"
    K3D_PATH: Path = ROOT_PATH / "k3d"

    debug: bool = env.bool("DEBUG", False)

    def __init__(self) -> None:
        self.database: dict[str, str] = {
            "driver": env.str("DATABASE_DRIVER"),
            "user": env.str("POSTGRES_USER"),
            "password": env.str("POSTGRES_PASSWORD"),
            "name": env.str("POSTGRES_DB"),
            "localhost": env.str("DATABASE_LOCALHOST"),
            "k8s_host": env.str("DATABASE_K8S_HOST"),
            "port": env.int("POSTGRES_PORT", 5432),
        }

    debug: bool = env.bool("DEBUG", False)

    def _build_database_url(self, host: str) -> str:
        driver = self.database["driver"]
        user = self.database["user"]
        password = self.database["password"]
        name = self.database["name"]
        port = self.database["port"]
        return f"{driver}://{user}:{password}@{host}:{port}/{name}"

    @property
    def database_localhost_url(self) -> str:
        """Construct the database URL for localhost from the individual components."""
        return self._build_database_url(self.database["localhost"])

    @property
    def database_k8s_host_url(self) -> str:
        """Construct the database URL for Kubernetes from the individual components."""
        return self._build_database_url(self.database["k8s_host"])


settings = Settings()
