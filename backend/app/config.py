from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "anime-companion"
    environment: str = "local"
    database_path: str = "data/anime_companion.db"
    llm_timeout_seconds: float = 30.0
    max_context_turns: int = 20

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_prefix="ANIME_COMPANION_",
        extra="ignore",
    )


settings = Settings()
