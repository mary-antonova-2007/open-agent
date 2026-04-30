from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "OpenAgentCRM"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "sqlite+aiosqlite:///./openagentcrm.db"
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str = "change-me"
    telegram_webhook_secret: str = "change-me"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_files: str = "company-files"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "company_knowledge"

    llm_base_url: str = "http://localhost:8080/v1"
    llm_api_key: str = "local-dev-key"
    llm_model: str = "local-model"
    embedding_model: str = "local-embedding-model"

    admin_telegram_user_id: int | None = Field(default=None)
    admin_full_name: str = "System Admin"

    @field_validator("admin_telegram_user_id", mode="before")
    @classmethod
    def empty_admin_telegram_user_id_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
