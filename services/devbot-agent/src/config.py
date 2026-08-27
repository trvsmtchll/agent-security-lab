"""Application configuration using pydantic settings."""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Demo
    demo_mode: Literal["live", "scripted"] = "live"
    prompt_style: Literal["default", "moderate"] = "default"

    # Database
    database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/api_docs"
    customers_database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/customers"

    # GitHub
    github_pat: str = ""
    github_exfil_repo: str = "attacker-org/diagnostics"

    # Wiki
    wiki_url: str = "http://wiki"

    # Attacker server
    attacker_server_url: str = "http://attacker-server:8080"

    # Server
    agent_host: str = "0.0.0.0"
    agent_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
