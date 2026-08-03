"""
app/mqtt/client.py
──────────────────
Creates and exports the shared FastMQTT instance.

HiveMQ Cloud requires TLS on port 8883.
We build an explicit ssl.SSLContext with CERT_REQUIRED + check_hostname=True
instead of relying on ssl=True (which calls ssl.create_default_context()
internally — same result, but explicit is safer and easier to debug).
"""

import ssl

from fastapi_mqtt import FastMQTT, MQTTConfig

from app.config import settings

# ── TLS context — verify HiveMQ Cloud's certificate against system CA store ───
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = True
_ssl_ctx.verify_mode = ssl.CERT_REQUIRED


mqtt_config = MQTTConfig(
    host=settings.mqtt_broker_url,
    port=settings.mqtt_port,
    keepalive=60,
    username=settings.mqtt_username,
    password=settings.mqtt_password,
    ssl=_ssl_ctx,            # explicit SSLContext — TLS with cert verification
    reconnect_retries=5,
    reconnect_delay=5,
)

# Single shared FastMQTT instance — imported by main.py and handlers.py
mqtt = FastMQTT(config=mqtt_config)
