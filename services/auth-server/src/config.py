"""Auth-server configuration using pydantic settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Issuer settings loaded from environment variables."""

    # Canonical identifiers (TM-11: written once, used everywhere)
    issuer: str = "http://auth-server:8085"
    mcp_resource_uri: str = "http://mcp-server:9000/mcp"

    # Registered client (lab has exactly one real client)
    oauth_client_id: str = "devbot-agent"
    oauth_client_secret: str = "CHANGE_ME"
    # Scope ceiling for the registered client (TM-04: issuer narrows to this)
    client_scope_ceiling: str = "tools:read tools:execute tools:write"

    token_ttl_seconds: int = 300

    # TM-03: kill switch for the broken-token fixture endpoints.
    # Default true in compose (it is the lab), false in k8s manifests.
    demo_fixtures_enabled: bool = True

    auth_host: str = "0.0.0.0"
    auth_port: int = 8085

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
