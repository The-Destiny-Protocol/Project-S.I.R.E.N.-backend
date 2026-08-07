# AGENTS.md — Contributor & AI Agent Guide

> This file documents the full context of this codebase so that any developer or AI coding assistant can understand the architecture, conventions, and known gotchas, and continue development without hand-holding.

---

## 1. Project Identity

| Field            | Value                                              |
|------------------|----------------------------------------------------|
| **Project**      | Ambulance Priority & De-Congestion System (Backend) |
| **Competition**  | Smart India Hackathon 2026                          |
| **Language**     | Python 3.13                                         |
| **Framework**    | FastAPI 0.115.6                                     |
| **Database**     | PostgreSQL + PostGIS (via Supabase)                  |
| **MQTT Broker**  | HiveMQ Cloud Free Tier (TLS on port 8883)            |
| **Auth**         | JWT (HS256) with bcrypt password hashing             |

---

## 2. Repository Layout

```
app/
├── main.py               # App factory + lifespan (DB init, MQTT connect/disconnect)
├── config.py             # pydantic-settings: typed env vars from .env
├── database.py           # Engine, SessionLocal, Base, init_db(), get_db()
│
├── core/
│   └── security.py       # get_password_hash(), verify_password(), create_access_token()
│
├── api/
│   ├── deps.py           # get_current_user(), RoleChecker (RBAC dependency)
│   └── routers/
│       ├── auth.py       # POST /auth/login, POST /auth/register
│       ├── map.py        # GET /map/ambulances, /map/police (PostGIS -> GeoJSON FeatureCollections)
│       └── websockets.py # WS /ws/live-map (Real-time telemetry broadcast via ConnectionManager)
│
├── models/               # SQLAlchemy 2.0 ORM mapped classes
│   ├── ambulance.py      # Ambulance — UUID PK, status, PostGIS POINT, updated_at
│   ├── police_unit.py    # PoliceUnit — UUID PK, unit_code, PostGIS POINT, updated_at
│   ├── incident.py       # EmergencyIncident — UUID PK, trigger_source, status
│   └── user.py           # User — UUID PK, username, hashed_password, role, is_active
│
├── schemas/              # Pydantic V2 models for request validation and response serialization
│
├── routers/              # REST route handlers
│   ├── ambulance.py      # POST /register (Admin), GET /active (Admin|Dispatcher)
│   ├── police.py         # GET /units (Admin|Dispatcher)
│   └── emergency.py      # POST /sos, GET /incidents/active, PATCH /resolve
│
├── services/
│   ├── geospatial.py     # find_nearest_police_unit() — PostGIS ST_Distance
│   ├── roip_service.py   # pyttsx3 offline TTS generation and HTTP dispatch to gateway
│   └── ws_manager.py     # ConnectionManager for Live Map WS broadcast
│
└── mqtt/
    ├── client.py         # FastMQTT singleton, SSLContext for HiveMQ Cloud TLS
    └── handlers.py       # on_message, telemetry→trigger pipeline + WS broadcast

discord_gateway/
└── discord_bot.py        # Standalone Discord Bot (Mock RoIP Gateway) on port 8001
```

---

## 3. Critical Conventions & Rules

### 3.1 RBAC Roles (Case-Sensitive)

The database stores roles as **exact strings**: `"Admin"` and `"Dispatcher"`.

- **Admin-only endpoints**: `Depends(RoleChecker(["Admin"]))`
- **Shared/view endpoints**: `Depends(RoleChecker(["Admin", "Dispatcher"]))`

> ⚠️ **NEVER use lowercase** (e.g., `"admin"`, `"standard_user"`, `"control_room"`) in `RoleChecker`. The check is case-sensitive and must match the database enum exactly.

### 3.2 Database Sessions

- **`get_db()`** (in `database.py`) is a generator that yields a session and closes it in `finally`.
- All write endpoints **must** call `db.commit()` explicitly inside a `try` block and `db.rollback()` in `except`. SQLAlchemy 2.0 does **not** auto-commit.
- Never rely on the session's `__del__` or pool-level cleanup to commit — it will silently rollback.

### 3.3 PostGIS Geometry

- All `location` columns use `Geometry(geometry_type="POINT", srid=4326)` (WGS-84).
- **Write path**: `from_shape(Point(lng, lat), srid=4326)` — note PostGIS convention: **(longitude, latitude)** not (lat, lng).
- **Read path**: `to_shape(row.location)` returns a Shapely `Point`, then `pt.y` = latitude, `pt.x` = longitude.
- **Geospatial queries**: Cast to `Geography()` type (not raw strings) when using `ST_Distance`. Raw strings cause `AttributeError: '_static_cache_key'` in SQLAlchemy 2.0.

### 3.4 MQTT

- The MQTT client is a **single shared `FastMQTT` instance** in `app/mqtt/client.py`.
- Handlers are registered via `@mqtt.on_connect()`, `@mqtt.on_message()` decorators in `app/mqtt/handlers.py`.
- Handlers are activated by side-effect import: `import app.mqtt.handlers` in `main.py`.
- MQTT lifecycle (`mqtt_startup` / `mqtt_shutdown`) is managed in the FastAPI `lifespan` context manager.
- Connection to HiveMQ Cloud uses **standard TLS + Username/Password** (not mTLS). The free tier does not support client certificates.
- Topic wildcard `+` (single level) is used for subscriptions, not `#`.

### 3.5 Pydantic

- This project uses **Pydantic V2** (`BaseModel`, `model_config`, `ConfigDict`).
- Use `Field(...)` with `description=` and `examples=` on response models to enrich Swagger docs.
- Use `model_config = {"from_attributes": True}` (not the V1 `orm_mode = True`).
- Default test coordinates are Bhubaneswar, India: `lat=20.2960`, `lng=85.8245`.

### 3.6 Configuration

- All secrets and connection strings are loaded from `.env` via `pydantic-settings`.
- The `Settings` class in `app/config.py` is instantiated once as `settings` and imported everywhere.
- **Never hardcode credentials** in source code. Use `.env` and `.env.example`.

---

## 4. Known Gotchas & Past Bugs

| Issue | Root Cause | Fix Applied |
|-------|-----------|-------------|
| `ROLLBACK` instead of `COMMIT` on 201 Created | `get_db()` lacked explicit rollback on exception, causing pool-level silent rollback | Added `try/except/rollback` pattern to all write endpoints and `get_db()` |
| `AttributeError: 'str' has no attribute '_static_cache_key'` | Raw Python string `"geography"` passed to `cast()` in SQLAlchemy 2.0 | Replaced with `GeoAlchemy2.Geography()` type instance |
| MQTT silently fails to connect | `fastapi-mqtt` requires explicit `mqtt_startup()` call during lifespan | Added `await mqtt.mqtt_startup()` inside `lifespan()` context manager |
| MQTT subscription not working on reconnect | Subscription was outside `on_connect` callback | Moved `client.subscribe()` into `handle_connect()` |
| RoleChecker returning 403 for valid users | Role strings were lowercase in code (`"admin"`) but stored as `"Admin"` in DB | Normalized all `RoleChecker` calls to use exact DB values |
| `gmqtt` `on_connect` `rc` is a `ReasonCode` object in MQTT v5 | Code compared `rc == 0` but `rc` was an object | Added `rc.value if hasattr(rc, "value") else int(rc)` normalization |

---

## 5. Dependency & Version Pinning

All dependencies are pinned in `requirements.txt`. Key version constraints:

- `sqlalchemy==2.0.36` — fixes Python 3.13 `FastIntFlag` incompatibility.
- `pydantic==2.10.6` — ships pre-built `cp313-win_amd64` wheels.
- `bcrypt==4.1.2` — pinned because `passlib` 1.7.4 may not support bcrypt 5.x.

Before upgrading any dependency, check for breaking changes in these areas.

---

## 6. Data Flow: Blocked Ambulance → Police Alert

```
1. Ambulance IoT device or Edge Vision AI publishes to:
   sih/ambulance/telemetry/{ambulance_id}
   Payload: {"status": "blocked", "lat": 20.2960, "lng": 85.8245}

2. handlers.py::handle_message() is invoked.
   a. Telemetry is broadcast via WebSockets (Live Map) immediately.

3. _handle_telemetry() runs:
   a. Upserts the ambulance's location and status in the DB.
   b. db.commit()

4. If status == "blocked" (or if POST /sos is hit directly):
   a. _trigger_nearest_police() calls find_nearest_police_unit(lat, lng, db)
   b. geospatial.py runs PostGIS ST_Distance query.
   c. Returns the nearest PoliceUnit ORM object.
   d. Saves an EmergencyIncident record to track the event.

5. Background TTS Task (roip_service.py) starts:
   a. Synthesizes a voice alert using `pyttsx3` into a `.wav` file.
   b. Dispatches the `.wav` file over HTTP POST to the Discord Mock Gateway (port 8001).

6. Discord Gateway (discord_bot.py) receives payload:
   a. Bot connects to the designated Discord Voice Channel.
   b. Streams the `.wav` file using FFmpegPCMAudio.
   c. Disconnects cleanly when finished.
```

---

## 7. How to Add a New Feature

### Adding a New REST Endpoint

1. **Schema** → Create Pydantic models in `app/schemas/`.
2. **Model** → If new table needed, create in `app/models/` and import it in `database.py::init_db()`.
3. **Router** → Create the route in `app/routers/` or `app/api/routers/`.
4. **RBAC** → Protect with `Depends(RoleChecker(["Admin"]))` or `Depends(RoleChecker(["Admin", "Dispatcher"]))`.
5. **Register** → Include the router in `app/main.py::create_app()`.

### Adding a New MQTT Topic Handler

1. Define the topic constant in `app/mqtt/handlers.py`.
2. Add logic inside `handle_message()` to route based on `topic_parts`.
3. If publishing, use `mqtt.publish(topic, payload, qos=1)`.

### Adding a New User Role

1. Add the role string to the `User.role` field's allowed values.
2. Update `RoleChecker` calls in the relevant routers.
3. Update `app/schemas/user.py::UserCreate.role` field description.

---

## 8. Environment & Tooling

- **Package Manager**: `pip` with `requirements.txt`.
- **Dev Server**: `uvicorn app.main:app --reload` (hot-reload enabled).
- **API Docs**: Swagger at `/docs`, ReDoc at `/redoc`.
- **Database**: PostgreSQL with PostGIS extension. Tables are auto-created on startup.
- **MQTT Broker**: HiveMQ Cloud (Free Tier). Configure via `.env`.
- **Preferred command**: Use `py` instead of `python` on Windows.

---

## 9. Testing Checklist (Manual)

Before merging any PR, verify:

- [ ] `GET /health` returns `{"status": "ok"}`.
- [ ] `POST /api/v1/auth/register` creates a user.
- [ ] `POST /api/v1/auth/login` returns a valid JWT.
- [ ] `GET /api/v1/ambulances/active` returns `401` without a token.
- [ ] `GET /api/v1/ambulances/active` returns `200` with a valid `Dispatcher` token.
- [ ] `POST /api/v1/ambulances/register` returns `403` with a `Dispatcher` token.
- [ ] `POST /api/v1/ambulances/register` returns `201` with an `Admin` token.
- [ ] MQTT telemetry with `"blocked"` status triggers a police alert publish.
- [ ] Swagger UI at `/docs` shows rich descriptions and examples for all schemas.
