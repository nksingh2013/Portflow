from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import NoDecode
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env" if (PROJECT_ROOT / ".env").exists() else BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PORTFLOW_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    demo_mode: bool = False
    jwt_secret: SecretStr = Field(min_length=32)
    database_url: str = "postgresql+psycopg://portflow_app@localhost:5432/portflow"
    redis_url: str = "redis://localhost:6379/0"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:8080"]
    token_issuer: str = "portflow"
    demo_admin_email: str = "admin@demo.portflow.local"
    demo_admin_password: SecretStr | None = None
    demo_customer_email: str = "customer@demo.portflow.local"
    demo_customer_password: SecretStr | None = None
    demo_admin_mfa_secret: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
