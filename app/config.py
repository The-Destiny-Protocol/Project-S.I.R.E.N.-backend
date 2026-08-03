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

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:password@localhost:5432/sih_ambulance"

    # ── MQTT (HiveMQ Cloud) ────────────────────────────────────────────────────
    mqtt_broker_url: str = "your-cluster.s1.eu.hivemq.cloud"
    mqtt_port: int = 8883
    mqtt_username: str = "your_hivemq_username"
    mqtt_password: str = "your_hivemq_password"


# Single settings instance imported by all modules
settings = Settings()
