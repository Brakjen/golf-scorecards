"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-based application configuration.

    Attributes:
        app_name: Display name of the application.
        app_env: Current environment (e.g. ``"development"``).
        debug: Whether debug mode is enabled.
        db_path: Filesystem path to the SQLite database file.
    """
    app_name: str = "Golf Scorecards API"
    app_env: str = "development"
    debug: bool = True
    db_path: str = "data/golf_scorecards.db"
    openai_api_key: str = ""
    app_password: str = ""
    session_secret: str = "dev-insecure-secret-change-me"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
