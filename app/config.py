"""
app/config.py
─────────────
Central settings management using pydantic-settings.
All values are read from environment variables (or a .env file at project root).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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

    # ── MQTT (HiveMQ Cloud / Broker) ───────────────────────────────────────────
    mqtt_broker_url: str = "your-cluster.s1.eu.hivemq.cloud"
    mqtt_port: int = 8883
    mqtt_username: str = "your_hivemq_username"
    mqtt_password: str = "your_hivemq_password"



# Single settings instance imported by all modules
settings = Settings()
