"""Application settings loaded from environment variables."""

from pathlib import Path

from environs import Env

env = Env()
env.read_env()


class Settings:
    # hallm/core/settings.py → hallm/core/ → hallm/ → repo root
    ROOT_PATH: Path = Path(__file__).parent.parent.parent
    K3D_PATH: Path = ROOT_PATH / "k3d"

    database_url: str = env.str("DATABASE_URL")
    debug: bool = env.bool("DEBUG", False)


settings = Settings()
