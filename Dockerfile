# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile
# Shared base image for both the FastAPI API server and the Discord gateway bot.
# Both services are launched via docker-compose with different CMD overrides.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.13-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# so logs appear immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg  : required by discord.py FFmpegPCMAudio to stream .wav audio in voice channels
# libpq-dev: required by psycopg2 (PostgreSQL driver)
# gcc     : required to compile some Python C-extensions (e.g. psycopg2-binary fallback)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libpq-dev \
        gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer.
# Only invalidated when requirements.txt actually changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY . .

# ── Default command (overridden per-service in docker-compose.yml) ────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
