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

    debug: bool = env.bool("DEBUG", False)

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
