# 🚑 Ambulance Priority & De-Congestion System — Backend

> **Smart India Hackathon 2026** · Real-time ambulance corridor management powered by PostGIS, MQTT, and JWT-secured REST APIs.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Server](#running-the-server)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Ambulances](#ambulances)
  - [Police Units](#police-units)
  - [Corridor](#corridor)
- [MQTT Topics](#mqtt-topics)
- [Authentication & RBAC](#authentication--rbac)
- [Database Schema](#database-schema)
- [Development Guide](#development-guide)
- [License](#license)

---

## Overview

This backend powers a city-scale ambulance priority system. When an ambulance encounters a traffic blockage, its onboard IoT device publishes a `"blocked"` telemetry event over MQTT. The backend then:

1. **Persists** the ambulance's GPS location to a PostGIS-enabled PostgreSQL database.
2. **Queries** the nearest police unit using geospatial `ST_Distance` calculations (in metres).
3. **Publishes** a flash-trigger alert to that police unit's MQTT topic, notifying them to clear the corridor.

The REST API layer serves the control-room dashboard and the simulation/frontend teams with the initial geographic state of all ambulances and police units.

---

## Architecture

```
┌──────────────────┐        MQTT (TLS:8883)        ┌──────────────────────┐
│  Ambulance IoT   │ ──── telemetry/{id} ────────▶ │   HiveMQ Cloud       │
│  Edge Device     │                                │   (Message Broker)   │
└──────────────────┘                                └──────────┬───────────┘
                                                               │
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │   FastAPI Backend     │
                                                    │  ┌────────────────┐  │
                                                    │  │ MQTT Handlers  │  │  ◀── subscribes to sih/ambulance/telemetry/+
                                                    │  │ (handlers.py)  │  │  ──▶ publishes to sih/police/trigger/{id}
                                                    │  └───────┬────────┘  │
                                                    │          │           │
                                                    │  ┌───────▼────────┐  │
                                                    │  │ Geospatial     │  │  ◀── ST_Distance via PostGIS
                                                    │  │ Service        │  │
                                                    │  └───────┬────────┘  │
                                                    │          │           │
                                                    │  ┌───────▼────────┐  │
                                                    │  │ PostgreSQL +   │  │
                                                    │  │ PostGIS        │  │
                                                    │  └───────┬────────┘  │
                                                    │          │           │
                                                    │  ┌───────▼────────┐  │
                                                    │  │ REST API       │  │  ◀── JWT-secured endpoints
                                                    │  │ WS Live Map    │  │  ◀── Real-time WS broadcasts
                                                    │  └───────┬────────┘  │
                                                    └──────────│───────────┘
                                                               │  HTTP POST (.wav)
                                                    ┌──────────▼───────────┐
                                                    │ Discord Gateway      │
                                                    │ (Mock RoIP Bot)      │  ──▶ Discord Voice Channel
                                                    └──────────────────────┘
```

---

## Tech Stack

| Layer           | Technology                                      |
|-----------------|--------------------------------------------------|
| **Framework**   | FastAPI 0.115.6 + Uvicorn 0.32.1                 |
| **Database**    | PostgreSQL + PostGIS (via Supabase or local)     |
| **ORM**         | SQLAlchemy 2.0.36 + GeoAlchemy2 0.15.2           |
| **Validation**  | Pydantic V2 (2.10.6) + pydantic-settings 2.7.1  |
| **MQTT**        | HiveMQ Cloud (Free Tier) via fastapi-mqtt / gmqtt|
| **Voice / RoIP**| pyttsx3 (TTS) + discord.py (Voice Gateway)       |
| **Auth**        | JWT (PyJWT 2.8.0) + bcrypt (passlib 1.7.4)      |
| **Language**    | Python 3.13                                      |

---

## Project Structure

```
SIH 2026/
├── Dockerfile                # Shared image for API and Discord bot
├── docker-compose.yml        # Orchestrates both services
├── .env.example              # Environment variable template
├── project_explanation.md    # Comprehensive architectural deep-dive
├── requirements.txt          # Pinned Python dependencies
├── discord_gateway/
│   └── discord_bot.py        # Standalone Mock RoIP Gateway (aiohttp + discord.py)
├── edge_node/
│   └── vision/               # YOLO AI vision anomaly detection (dashcam sim)
│
└── app/
    ├── main.py               # FastAPI app factory, lifespan (DB + MQTT init)
    ├── database.py           # SQLAlchemy engine, SessionLocal, Base, init_db()
    │
    ├── models/               # SQLAlchemy ORM models (Ambulance, PoliceUnit, User, Incident)
    ├── schemas/              # Pydantic V2 request/response models
    │
    ├── api/routers/          # REST endpoint groups
    │   ├── map.py            # GET /ambulances, /police (GeoJSON points)
    │   ├── websockets.py     # WS /live-map (Real-time telemetry broadcast)
    │   └── auth.py           # JWT auth
    │
    ├── routers/              # Domain endpoints
    │   ├── emergency.py      # POST /sos, GET /incidents/active, PATCH /resolve
    │   ├── ambulance.py      
    │   └── police.py         
    │
    ├── services/
    │   ├── geospatial.py     # find_nearest_police_unit() — PostGIS ST_Distance
    │   ├── roip_service.py   # pyttsx3 offline TTS generation and HTTP dispatch
    │   └── ws_manager.py     # ConnectionManager for Live Map broadcast
    │
    └── mqtt/
        ├── client.py         # FastMQTT + TLS SSLContext configuration
        └── handlers.py       # on_message, telemetry → trigger flow + WS broadcast
```

---

## Getting Started

### Prerequisites

| Requirement       | Minimum Version | Notes                                       |
|-------------------|-----------------|----------------------------------------------|
| Python            | 3.11+           | Tested on 3.13                               |
| PostgreSQL        | 14+             | With PostGIS extension enabled               |
| HiveMQ Cloud      | Free Tier       | Or any MQTT 3.1.1/5.0 broker with TLS       |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/SIH-2026.git
cd SIH-2026

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

### Environment Variables

```bash
# Copy the template and fill in your real values
cp .env.example .env
```

| Variable                      | Required | Description                                    |
|-------------------------------|----------|------------------------------------------------|
| `DATABASE_URL`                | ✅       | PostgreSQL connection string (PostGIS enabled) |
| `MQTT_BROKER_URL`             | ✅       | HiveMQ Cloud cluster hostname                 |
| `MQTT_PORT`                   | ✅       | Broker TLS port (default: `8883`)              |
| `MQTT_USERNAME`               | ✅       | MQTT broker username                           |
| `MQTT_PASSWORD`               | ✅       | MQTT broker password                           |
| `SECRET_KEY`                  | ✅       | JWT signing key (use `secrets.token_hex(32)`)  |
| `ALGORITHM`                   | ❌       | JWT algorithm (default: `HS256`)               |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌       | Token TTL in minutes (default: `30`)           |
| `APP_ENV`                     | ❌       | `development` or `production`                  |

### Running the Server (Docker - Recommended)

The easiest way to run the entire backend stack (API + Discord Gateway) is via Docker Compose:

```bash
# Build and start in background
docker compose up -d --build

# View logs
docker compose logs -f api
docker compose logs -f discord-gateway
```

### Running Locally (Without Docker)

```bash
# Terminal 1: FastAPI Server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Discord RoIP Bot
python discord_gateway/discord_bot.py
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Reference

All endpoints are prefixed with `/api/v1`. Protected endpoints require a Bearer JWT token in the `Authorization` header.

### Authentication

| Method | Endpoint               | Auth     | Description                        |
|--------|------------------------|----------|------------------------------------|
| POST   | `/api/v1/auth/register`| None     | Register a new user (Admin/Dispatcher) |
| POST   | `/api/v1/auth/login`   | None     | Login and receive a JWT token      |

**Login** uses OAuth2 `application/x-www-form-urlencoded` (`username` + `password`).

### Ambulances

| Method | Endpoint                       | Role Required        | Description                              |
|--------|--------------------------------|----------------------|------------------------------------------|
| POST   | `/api/v1/ambulances/register`  | `Admin`              | Register a new ambulance with GPS coords |
| GET    | `/api/v1/ambulances/active`    | `Admin`, `Dispatcher`| List all active ambulances               |
| POST   | `/api/v1/ambulances/seed-police`| `Admin`             | [Dev] Seed a police unit for testing     |

### Police Units

| Method | Endpoint                  | Role Required        | Description                     |
|--------|---------------------------|----------------------|---------------------------------|
| GET    | `/api/v1/police/units`    | `Admin`, `Dispatcher`| List all police unit locations  |

### Emergency / Incidents (SOS)

| Method | Endpoint                                 | Role Required        | Description                                      |
|--------|------------------------------------------|----------------------|--------------------------------------------------|
| POST   | `/api/v1/emergency/ambulances/{id}/sos`  | None                 | Triggers pipeline: Nearest Police + Voice Alert  |
| GET    | `/api/v1/emergency/incidents/active`     | `Admin`, `Dispatcher`| List all active incidents with nested context    |
| PATCH  | `/api/v1/emergency/incidents/{id}/resolve`| `Admin`, `Dispatcher`| Resolve an incident                              |

### Live Map / Dashboard (GeoJSON & WS)

| Method | Endpoint                        | Role Required        | Description                                      |
|--------|---------------------------------|----------------------|--------------------------------------------------|
| GET    | `/api/v1/map/ambulances`        | `Admin`, `Dispatcher`| All ambulances as GeoJSON FeatureCollection      |
| GET    | `/api/v1/map/police`            | `Admin`, `Dispatcher`| All police units as GeoJSON FeatureCollection    |
| WS     | `/api/v1/ws/live-map`           | None                 | Real-time MQTT telemetry broadcast               |

### Health

| Method | Endpoint   | Auth | Description         |
|--------|------------|------|---------------------|
| GET    | `/health`  | None | Health check        |

---

## MQTT Topics

| Topic                                 | Direction | QoS | Description                                                      |
|---------------------------------------|-----------|-----|------------------------------------------------------------------|
| `sih/ambulance/telemetry/{id}`        | Inbound   | 1   | Ambulance publishes `{ "status", "lat", "lng" }`                |
| `sih/police/trigger/{police_unit_id}` | Outbound  | 1   | Backend publishes `{ "flash": true, "ambulance_id": "..." }`   |

### Telemetry Payload Format

```json
{
  "status": "blocked",
  "lat": 20.2960,
  "lng": 85.8245
}
```

- `status`: `"active"` (normal) or `"blocked"` (traffic jam — triggers nearest police alert).
- `lat` / `lng`: WGS-84 GPS coordinates.

---

## Authentication & RBAC

The system uses **JWT (JSON Web Tokens)** for stateless authentication and a **Role-Based Access Control** model.

### Roles

| Role         | Permissions                                                        |
|--------------|--------------------------------------------------------------------|
| `Admin`      | Full access — register ambulances, seed police units, view all data |
| `Dispatcher` | Read-only access — view active ambulances, police units, corridor   |

### How It Works

1. **Register** a user via `POST /api/v1/auth/register` with a `role` field (`"Admin"` or `"Dispatcher"`).
2. **Login** via `POST /api/v1/auth/login` to receive a JWT access token.
3. **Include the token** in subsequent requests: `Authorization: Bearer <token>`.
4. Protected endpoints use `Depends(RoleChecker(["Admin", "Dispatcher"]))` to enforce RBAC at the route level. Unauthorized access returns **HTTP 403 Forbidden**.

### Quick Test (cURL)

```bash
# 1. Register an Admin user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin1234", "role": "Admin"}'

# 2. Login to get a JWT
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin&password=admin1234"

# 3. Use the token
curl -X GET http://localhost:8000/api/v1/ambulances/active \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

---

## Database Schema

The application uses **3 tables**, auto-created on startup via `Base.metadata.create_all()`.

### `ambulances`
| Column         | Type                  | Description                                 |
|----------------|-----------------------|---------------------------------------------|
| `id`           | UUID (PK)             | Unique ambulance identifier                 |
| `operator_type`| VARCHAR(50)           | `GOVT`, `PRIVATE`, `NGO`                    |
| `status`       | VARCHAR(20)           | `active`, `blocked`, `inactive`             |
| `location`     | GEOMETRY(POINT, 4326) | PostGIS point (longitude, latitude) WGS-84  |
| `updated_at`   | TIMESTAMPTZ           | Auto-updated on each telemetry event        |

### `police_units`
| Column       | Type                  | Description                                   |
|--------------|-----------------------|-----------------------------------------------|
| `id`         | UUID (PK)             | Unique police unit identifier                 |
| `unit_code`  | VARCHAR(50)           | Human-readable call-sign (e.g. `OD-PCR-001`) |
| `location`   | GEOMETRY(POINT, 4326) | PostGIS point (longitude, latitude) WGS-84    |
| `updated_at` | TIMESTAMPTZ           | Last update timestamp                          |

### `users`
| Column           | Type          | Description                          |
|------------------|---------------|--------------------------------------|
| `id`             | UUID (PK)     | Unique user identifier               |
| `username`       | VARCHAR(255)  | Unique login name                    |
| `hashed_password`| VARCHAR(255)  | bcrypt hash                          |
| `role`           | VARCHAR(50)   | `Admin` or `Dispatcher`              |
| `is_active`      | BOOLEAN       | Account enabled flag                 |
| `created_at`     | TIMESTAMPTZ   | Account creation time                |
| `updated_at`     | TIMESTAMPTZ   | Last profile update                  |

> **Note:** The PostGIS extension (`CREATE EXTENSION IF NOT EXISTS postgis`) is automatically enabled in `init_db()`.

---

## Development Guide

### Default Test Coordinates

All schemas default to **Bhubaneswar, Odisha, India**:
- Latitude: `20.2960`
- Longitude: `85.8245`

### Key Design Decisions

1. **Lazy/Non-Fatal Startup**: The MQTT broker connection is wrapped in `try/except` during startup. If the broker is unreachable, REST endpoints still work.
2. **Explicit Transaction Management**: All database write endpoints use explicit `db.commit()` / `db.rollback()` to avoid silent SQLAlchemy pool-level rollbacks.
3. **Geography Casting**: Geospatial queries use `GeoAlchemy2.Geography()` type for `ST_Distance` to get accurate metre-based distances instead of degree-based approximations.
4. **Standard TLS (not mTLS)**: The MQTT client uses `ssl.create_default_context()` with Username/Password for HiveMQ Cloud Free Tier compatibility.

### Adding a New Endpoint

1. Define the Pydantic schema in `app/schemas/`.
2. Create the route function in `app/routers/` (or `app/api/routers/` for auth-related).
3. Protect it with `Depends(RoleChecker(["Admin"]))` or `Depends(RoleChecker(["Admin", "Dispatcher"]))`.
4. Register the router in `app/main.py` → `create_app()`.

### Useful Commands

```bash
# Generate a secure JWT secret
python -c "import secrets; print(secrets.token_hex(32))"

# Check PostGIS is working
psql $DATABASE_URL -c "SELECT PostGIS_Version();"
```

---

## License

This project is part of the **Smart India Hackathon 2026** initiative. See the team for licensing terms.
