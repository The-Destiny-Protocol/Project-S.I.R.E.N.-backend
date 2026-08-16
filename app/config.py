"""
app/config.py
─────────────
Central settings management using pydantic-settings.
All values are read from environment variables (or a .env file at project root).
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_title: str = "Ambulance Priority & De-Congestion API"
    app_version: str = "1.0.0"

    # ── Mapbox ─────────────────────────────────────────────────────────────────
    mapbox_access_token: str = ""

    # ── Security (JWT) ─────────────────────────────────────────────────────────
    # In production, ensure SECRET_KEY is set in .env with a strong random string.
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:password@localhost:5432/sih_ambulance"
    redis_url: str = "redis://localhost:6379"

    @field_validator("database_url")
    def assemble_db_connection(cls, v: str | None) -> str:
        """
        Sanitize Supabase URLs (and others) that might use `postgres://`.
        SQLAlchemy 1.4+ requires `postgresql://`.
        """
        if v and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v or ""

    # ── CORS Origins ───────────────────────────────────────────────────────────
    # Comma-separated list in .env, e.g., "http://localhost:3000,https://my-frontend.vercel.app"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

    # ── MQTT (HiveMQ Cloud / Broker) ───────────────────────────────────────────
    mqtt_broker_url: str = "your-cluster.s1.eu.hivemq.cloud"
    mqtt_port: int = 8883
    mqtt_username: str = "your_hivemq_username"
    mqtt_password: str = "your_hivemq_password"

    # ── Discord RoIP Gateway Bot ──────────────────────────────────────────────
    discord_bot_token: str = ""
    discord_voice_channel_id: int = 0
    
    # ── AWS Polly ──────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "ap-south-1"



# Single settings instance imported by all modules
settings = Settings()
