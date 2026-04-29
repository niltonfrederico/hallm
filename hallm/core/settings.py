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
    litellm_model: str = env.str("LITELLM_MODEL", "openai/gpt-4o-mini")
    llm_timeout: int | None = env.int("LLM_TIMEOUT", None)
    debug: bool = env.bool("DEBUG", False)


settings = Settings()
