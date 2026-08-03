"""
app/mqtt/client.py
──────────────────
Creates and exports the shared FastMQTT instance.

All MQTT configuration is loaded from environment variables via app.config.settings.
TLS is enabled — HiveMQ Cloud requires port 8883 with SSL/TLS.
"""

from fastapi_mqtt import FastMQTT, MQTTConfig

from app.config import settings

mqtt_config = MQTTConfig(
    host=settings.mqtt_broker_url,
    port=settings.mqtt_port,
    keepalive=60,
    username=settings.mqtt_username,
    password=settings.mqtt_password,
    ssl=True,            # HiveMQ Cloud mandates TLS on port 8883
    reconnect_retries=5,
    reconnect_delay=5,
)

# Single shared FastMQTT instance — imported by main.py and handlers.py
mqtt = FastMQTT(config=mqtt_config)
