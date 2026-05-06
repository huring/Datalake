from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_token: str = Field(min_length=1, alias="API_TOKEN")
    database_url: str = Field(default="sqlite:////data/datalake.db", alias="DATABASE_URL")
    app_version: str = Field(default="1.0.0", alias="API_VERSION")
    log_level: str = Field(default="info", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
