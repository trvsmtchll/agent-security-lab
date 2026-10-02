"""MCP-server configuration using pydantic settings."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Resource-server settings loaded from environment variables."""

    # Canonical identifiers (TM-11)
    oauth_issuer: str = "http://auth-server:8085"
    jwks_url: str = "http://auth-server:8085/.well-known/jwks.json"
    canonical_uri: str = "http://mcp-server:9000/mcp"  # == aud

    # Enforcement toggles
    auth_mode: Literal["enforce", "off"] = "enforce"  # demo act 1 (off) vs acts 2-3 (enforce)
    auth_failure_mode: Literal["fail_closed", "fail_open"] = "fail_closed"  # TM-08/§4

    jwks_cache_ttl: int = 300
    clock_leeway_seconds: int = 30

    # Upstream credentials — the SERVER'S OWN, never the inbound token (TM-13)
    database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/api_docs"
    customers_database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/customers"
    github_pat: str = ""
    github_exfil_repo: str = "attacker-org/diagnostics"

    mcp_host: str = "0.0.0.0"
    mcp_port: int = 9000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
