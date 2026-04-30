"""Application settings loaded from environment variables."""

from pathlib import Path

from environs import Env

env = Env()
env.read_env()


class Settings:
    # hallm/core/settings.py → hallm/core/ → hallm/ → repo root
    ROOT_PATH: Path = Path(__file__).parent.parent.parent
    CLI_PATH: Path = ROOT_PATH / "cli"
    K3D_PATH: Path = ROOT_PATH / "k3d"

    debug: bool = env.bool("DEBUG", False)

    def __init__(self) -> None:
        self.database: dict[str, str] = {
            "driver": env.str("DATABASE_DRIVER"),
            "user": env.str("POSTGRES_USER"),
            "password": env.str("POSTGRES_PASSWORD"),
            "name": env.str("POSTGRES_DB"),
            "host": env.str("POSTGRES_HOST", "postgres"),
        }

    debug: bool = env.bool("DEBUG", False)

    @property
    def database_url(self) -> str:
        """Construct the database URL from the individual components."""
        driver = self.database["driver"]
        user = self.database["user"]
        password = self.database["password"]
        host = self.database["host"]
        name = self.database["name"]
        return f"{driver}://{user}:{password}@{host}/{name}"


settings = Settings()
