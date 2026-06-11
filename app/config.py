from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Elastic On-Call Agent"
    app_env: str = "local"

    elastic_url: str = ""
    elastic_api_key: str = ""

    google_cloud_project: str = ""
    google_cloud_location: str = "europe-west1"
    gemini_model: str = "gemini-2.0-flash"

    demo_token: str = "local-demo-token"
    slack_webhook_url: str = ""
    remediation_mode: str = "simulate"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
