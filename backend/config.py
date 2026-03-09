from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://clanker:clanker@localhost:5432/clanker_gauntlet"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth
    auth_provider: Literal["auth0", "jwt"] = "jwt"

    # Auth0
    auth0_domain: str = ""
    auth0_client_id: str = ""
    auth0_client_secret: str = ""
    auth0_audience: str = ""

    # JWT (via authlib)
    jwt_secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # Encryption (Fernet key for user API keys at rest)
    encryption_key: str = ""

    # Anthropic platform key
    anthropic_api_key: str = ""

    @property
    def sync_database_url(self) -> str:
        """Alembic-compatible synchronous URL derived from the async URL."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


settings = Settings()
