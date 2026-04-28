"""Application settings loaded from environment variables."""

from environs import Env

env = Env()
env.read_env()


class Settings:
    database_url: str = env.str("DATABASE_URL")
    litellm_model: str = env.str("LITELLM_MODEL", "openai/gpt-4o-mini")
    debug: bool = env.bool("DEBUG", False)


settings = Settings()
