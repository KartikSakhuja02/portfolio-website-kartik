from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_max_tokens: int = 500
    aws_region: str = "us-east-1"
    aws_ec2_instance_id: str = ""
    aws_lb_name: str = ""
    github_username: str = ""
    github_token: str = ""
    openrouter_site_url: str = ""
    openrouter_app_name: str = ""
    database_url: str = "postgresql+psycopg://portfolio:portfolio@localhost:5432/portfolio_ai"
    admin_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
