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

    # --- Authenticated MCP (default OFF; scripted mode never needs these) ---
    mcp_enabled: bool = False
    mcp_server_url: str = "http://mcp-server:9000/mcp"
    oauth_token_url: str = "http://auth-server:8085/token"
    oauth_client_id: str = "devbot-agent"
    oauth_client_secret: str = "CHANGE_ME"
    oauth_scope: str = "tools:read tools:execute tools:write"
    auth_failure_mode: Literal["fail_closed", "fail_open"] = "fail_closed"
    jwks_cache_ttl: int = 300

    # Server
    agent_host: str = "0.0.0.0"
    agent_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
