# EXPLANATION.md: Ambulance Priority & De-Congestion System (Backend)

This document serves as an exhaustive, end-to-end technical documentation file for the backend system of the Ambulance Priority & De-Congestion System. 

It is divided into three main parts:
1. **The Human-Friendly Guide:** A simple, jargon-free explanation of what this project does and the technology behind it.
2. **The Exhaustive Technical Reference:** A deep-dive for developers, outlining every single file, API endpoint, system layer, and data lifecycle.
3. **Deep-Dive Mechanisms:** A highly detailed breakdown of *exactly* how the Simulator, the Edge AI, and the Preemption Math actually work under the hood.

---

## PART 1: The Human-Friendly Guide (For Non-Tech Readers)

### 1. What Does This Project Do?
Imagine you are an ambulance driver rushing a critical patient to the hospital. Every second counts, but as you approach a busy intersection, the light turns red, and traffic is gridlocked. This delay could mean the difference between life and death.

**This project solves that problem.** It is a smart, automated system designed to give ambulances a "green corridor"—an uninterrupted path of green traffic lights from the moment they pick up a patient until they reach the hospital. 

Here is how the magic happens:
- **Tracking:** Every ambulance has a GPS tracker sending its location to our system every single second.
- **Smart AI Cameras (Edge Nodes):** Cameras at intersections use Artificial Intelligence to listen for ambulance sirens and "see" traffic jams or accidents.
- **Automated Green Lights:** As the ambulance drives, the system calculates which way it is pointing and how fast it is going. If it is approaching a red light, the system automatically talks to the traffic light and forces it to turn green *before* the ambulance arrives. Once the ambulance passes, the light goes back to normal.
- **Emergency Police Backup (SOS):** If an ambulance gets totally stuck in a jam and can't move, the driver hits an SOS button. The system immediately scans the map, finds the nearest police patrol car, and sends an automated voice message to the police radios saying, "Ambulance stuck at Intersection X, please assist!"

### 2. The Tech Stack (The Tools We Used & Why)
We used modern, high-performance tools to build this system because it needs to be incredibly fast. A 10-second delay in processing could mean the ambulance hits a red light.

- **FastAPI (The Brain):** A super-fast web framework built in Python. We use it to process all the incoming data, talk to the database, and serve our web dashboard. It was chosen because it can handle thousands of requests per second simultaneously.
- **PostgreSQL & PostGIS (The Map Database):** A specialized database that understands "geography." Instead of just storing words and numbers, it stores points on a map (latitude and longitude). It allows us to ask complex questions like, "Which police car is physically closest to this specific ambulance?" and get an answer instantly.
- **MQTT / HiveMQ (The Nervous System):** A lightning-fast messaging system originally designed for satellites. We use it because when an ambulance sends its GPS location, it doesn't need to load a web page; it just sends a tiny, instant pulse of data. MQTT routes these pulses in milliseconds.
- **WebSockets (The Live TV):** A technology that keeps a permanent open line between our server and the web browser. This allows the map on the dispatcher's screen to show the ambulances moving smoothly in real-time, just like watching an Uber approach on your phone.
- **YOLOv8 & PyTorch (The AI Eyes and Ears):** State-of-the-art Artificial Intelligence models that look at video feeds to detect cars, accidents, and listen to audio to identify the exact sound signature of an ambulance siren.

---

## PART 2: The Exhaustive Technical Reference

This section provides a thorough breakdown of the system architecture, file map, API endpoints, and system layers.

### 3. High-Level Architecture & System Design

The project is built around a hybrid micro-services and event-driven architecture designed to process high-throughput real-time spatial data. 

**Core Paradigms:**
- **Event-Driven Telemetry:** Uses MQTT (HiveMQ Cloud via TLS) to handle high-frequency location data streams (1Hz per ambulance) completely decoupled from the REST API. This ensures that the web server doesn't get bogged down by thousands of GPS pings.
- **Spatial GIS Processing:** PostgreSQL with the PostGIS extension is used to run dynamic geospatial queries. We use `ST_Distance` on geography types to find nearest neighbors and calculate vectors (Field of View) based on WGS-84 projections.
- **Real-Time Broadcasts:** FastAPI WebSockets (`ConnectionManager`) broadcast live positions to the frontend React dashboards instantly as they are ingested via MQTT.
- **Role-Based Access Control (RBAC):** Centralized permission system using JWT tokens (HS256) enforcing access for strictly-defined roles (`Admin`, `Dispatcher`).
- **Edge Computing Integration:** Separate edge-node modules process vision (YOLOv8) and audio (Siren Classification) locally and push triggered alerts to the central backend. This prevents sending heavy video feeds over the network.

**Component Interaction Flow:**
```text
[Edge AI Nodes / Mobile Apps] ---(MQTT: Telemetry 1Hz)---> [HiveMQ Cloud Broker]
                                                                    |
                                                                    v
                                                     [app/mqtt/handlers.py (FastMQTT)]
                                                                    |
                                         +--------------------------+--------------------------+
                                         |                          |                          |
                                         v                          v                          v
[FastAPI REST Clients]             [WebSocket Manager]        [Redis / PostGIS]         [Spatial Engine]
 (Admin / Dispatcher) ---> (HTTP)  (Live React Maps)         (State Persistence)      (FOV & Preemption)
                                                                                               |
                                                                                               v
                                                                                   [Discord Bot / RoIP Gateway]
```

---

### 4. Comprehensive API Endpoint Documentation

The FastAPI application exposes a rich set of REST endpoints. All endpoints under `/api/v1` (except login/register) are secured via JWT bearer tokens.

#### Authentication (`/api/v1/auth`)
- **`POST /auth/register`**
  - **Purpose:** Creates a new user in the system.
  - **Payload:** `{ "username": "string", "password": "strongpassword", "role": "Admin|Dispatcher" }`
  - **Response:** 201 Created. Returns the newly created user object (without the password).
- **`POST /auth/login`**
  - **Purpose:** Authenticates a user and returns a JSON Web Token (JWT).
  - **Payload:** OAuth2 Form Data (`username`, `password`).
  - **Response:** 200 OK. Returns `{ "access_token": "eyJhb...", "token_type": "bearer" }`.

#### Live Map Data (`/api/v1/map`)
- **`GET /map/ambulances`**
  - **Purpose:** Fetches the last known locations of all active ambulances to render on the map.
  - **Response:** 200 OK. Returns a strictly formatted GeoJSON `FeatureCollection` where each feature is a `Point` representing an ambulance.
- **`GET /map/police`**
  - **Purpose:** Fetches the locations of all active police units.
  - **Response:** 200 OK. Returns a GeoJSON `FeatureCollection`.
- **`GET /map/traffic-signals`**
  - **Purpose:** Retrieves the locations and current light states (Red/Green/Yellow) of all traffic intersections.
  - **Response:** 200 OK. Returns a GeoJSON `FeatureCollection`.
- **`GET /map/hospitals`**
  - **Purpose:** Retrieves all hospital nodes.
  - **Response:** 200 OK. Returns a GeoJSON `FeatureCollection`.

#### WebSockets (`/ws`)
- **`WS /ws/live-map`**
  - **Purpose:** An open socket connection for frontend dashboards. Pushes live telemetry updates (ambulances moving) and traffic light state changes instantly.

#### Ambulances (`/api/v1/ambulances`)
- **`POST /ambulances/register`**
  - **Purpose:** Onboards a new ambulance into the database.
  - **Payload:** `{ "registration_number": "MH01AB1234", "operator_type": "GOVT|PRIVATE" }`
  - **Response:** 201 Created. Returns the generated UUID for the vehicle.
- **`GET /ambulances/active`**
  - **Purpose:** Lists all ambulances that currently have a status of 'moving' or 'emergency'.
  - **Response:** 200 OK. JSON list of ambulance records.

#### Traffic Control & Overrides (`/api/v1/traffic`)
- **`POST /traffic/override`**
  - **Purpose:** Allows a dispatcher to manually force a traffic light to turn green.
  - **Payload:** `{ "intersection_id": "UUID", "state": "GREEN", "duration": 60 }`
  - **Response:** 200 OK. Confirms the override has been dispatched via MQTT to the hardware.

#### Emergency & SOS (`/api/v1/emergency`)
- **`POST /emergency/sos`**
  - **Purpose:** Triggered when an ambulance gets stuck. Creates an incident and dispatches police.
  - **Payload:** `{ "ambulance_id": "UUID", "trigger_source": "MANUAL|AI_DETECTION" }`
  - **Response:** 201 Created. Returns the incident ID and the dispatched Police Unit details.
- **`PATCH /emergency/resolve/{incident_id}`**
  - **Purpose:** Marks an active emergency as resolved, releasing the police unit back to normal patrol.
  - **Response:** 200 OK.

#### Route Calculations (`/api/v1/routing`)
- **`POST /routing/calculate`**
  - **Purpose:** Hits the external OSRM engine to plot the fastest path from the ambulance to the hospital.
  - **Payload:** `{ "start_lat": 20.1, "start_lng": 85.1, "end_lat": 20.2, "end_lng": 85.2 }`
  - **Response:** 200 OK. Returns an array of coordinates (Polyline) to be drawn on the map.

---

### 5. Exhaustive Directory & File Map

#### Root Directory
- **`.dockerignore`**: Excludes unnecessary files (like `.git`, `__pycache__`) from the Docker build context.
- **`.env`**: Contains sensitive environment variables like database credentials, JWT secrets, and MQTT broker details.
- **`.env.example`**: Template file outlining all required environment variables without exposing sensitive values.
- **`.gitignore`**: Specifies intentionally untracked files that Git should ignore.
- **`AGENTS.md`**: Technical context rules and conventions file intended for AI coding assistants and developers.
- **`docker-compose.yml`**: Defines multi-container orchestration for local development, primarily spinning up the FastAPI service and databases.
- **`Dockerfile`**: A multi-stage Docker build recipe to construct the backend application image safely and minimally.
- **`project_explanation.md`**: High-level overview of the competition problem statement, solution, and features.
- **`README.md`**: Project setup instructions, prerequisites, and execution commands.
- **`requirements.txt`**: Pinned Python dependencies (FastAPI, SQLAlchemy, Pydantic, etc.).
- **`seed.py`**: A utility script for initial database population.
- **`seed_db.py`**: A robust seeding script that populates the PostGIS database with mock intersections, hospitals, and police units from JSON files.
- **`simulate_ambulance.py`**: A standalone decoupled fleet simulator that generates dummy moving ambulance data and publishes it to MQTT to test the system without real vehicles.
- **`yolov8n.pt`**: Pre-trained YOLOv8 weights file for base object detection in edge nodes.

#### `app/` Directory (Core Backend)
- **`config.py`**: Defines the `Settings` class using `pydantic-settings` to safely load and type-cast variables from `.env`.
- **`database.py`**: Configures the SQLAlchemy 2.0 engine, `SessionLocal` factory, declarative base, and the `get_db()` dependency generator for safe database connections.
- **`main.py`**: The FastAPI application factory. Wires up routers, CORS middleware, and manages the lifespan context (database table initialization and MQTT connect/disconnect).
- **`__init__.py`**: Marks the directory as a Python package.

#### `app/api/` Directory (API Layer & Dependencies)
- **`deps.py`**: Contains dependency injection functions like `get_db` (for database sessions), `get_current_user` (for token decoding), and the `RoleChecker` class for strict RBAC enforcement.
- **`routers/auth.py`**: The authentication controller.
- **`routers/map.py`**: The GeoJSON generator controller for the live map.
- **`routers/websockets.py`**: The WebSocket entrypoint for the frontend.

#### `app/core/` Directory (Security)
- **`security.py`**: Contains utility functions for hashing passwords securely with `bcrypt`, verifying hashes, and generating stateless JWTs (`create_access_token`).

#### `app/models/` Directory (SQLAlchemy ORM)
- **`__init__.py`**: Marks the directory as a Python package.
- **`ambulance.py`**: Defines the `Ambulance` table (UUID, status, GeoAlchemy `POINT` for location, speed, route).
- **`hospital.py`**: Defines the `Hospital` table (UUID, name, capacity, PostGIS location).
- **`incident.py`**: Defines the `EmergencyIncident` table tracking SOS events, resolutions, and trigger sources.
- **`police_unit.py`**: Defines the `PoliceUnit` table for tracking moving or stationary police patrol cars.
- **`traffic.py`**: Defines the `TrafficSignal` table handling intersection nodes and their active red/green light states.
- **`user.py`**: Defines the `User` table for authentication (username, hashed_password, role enum).

#### `app/mqtt/` Directory (Messaging Layer)
- **`__init__.py`**: Marks the directory as a Python package.
- **`client.py`**: Instantiates the `FastMQTT` singleton object, configuring SSL/TLS contexts required for secure connection to HiveMQ Cloud.
- **`handlers.py`**: Defines the topic subscriptions and the core `on_message` callbacks that process incoming telemetry, cache states, and broadcast to websockets. This is the heart of the real-time system.

#### `app/routers/` Directory (Standard REST Endpoints)
- **`__init__.py`**: Marks the directory as a Python package.
- **`ambulance.py`**: CRUD operations for ambulances.
- **`corridor.py`**: Endpoints responsible for manually or algorithmically requesting green corridors.
- **`emergency.py`**: Endpoints for handling SOS POST requests and querying active incidents.
- **`hospital.py`**: CRUD endpoints for querying registered medical facilities.
- **`police.py`**: Endpoints for tracking police units and assigning them to incidents.
- **`routing.py`**: Interfaces with `routing_service.py` to calculate paths.
- **`traffic.py`**: Endpoints for manually toggling traffic lights or querying intersection statuses.

#### `app/schemas/` Directory (Pydantic Models)
- **`__init__.py`**: Marks the directory as a Python package.
- **`ambulance.py`**: Pydantic models validating ambulance creation requests and serialization for responses.
- **`incident.py`**: Pydantic models for incident payloads (e.g., trigger_source validation).
- **`police_unit.py`**: Pydantic models for police unit structures.
- **`traffic.py`**: Pydantic models for traffic signals (validating light states).
- **`user.py`**: Pydantic models for user registration (`UserCreate`), JWT Token responses, and UserOut serialization.

#### `app/services/` Directory (Business Logic)
- **`__init__.py`**: Marks the directory as a Python package.
- **`geospatial.py`**: Contains complex PostGIS logic, utilizing `ST_Distance` on `Geography` types to find nearest entities accurately on the globe.
- **`roip_service.py`**: Handles Text-To-Speech (pyttsx3) and dispatching audio alerts via HTTP webhooks to Discord.
- **`routing_service.py`**: An adapter for calling the external OSRM (Open Source Routing Machine) API to generate navigation polylines.
- **`ws_manager.py`**: Defines the `ConnectionManager` class controlling active WebSocket client connections and broadcasting JSON payloads.

#### `discord_gateway/` Directory
- **`discord_bot.py`**: A separate, lightweight script using `discord.py` to act as a mock Radio-over-IP (RoIP) gateway, playing TTS alerts in voice channels to simulate police radios.

#### `edge_node/` Directory (IoT AI Hardware Simulators)
- **`main_edge.py`**: Entry point for edge simulation orchestrating vision and audio feeds.
- **`audio/siren_classifier.py`**: Logic for extracting audio spectrograms and detecting ambulance sirens using AI.
- **`vision/anomaly_detection.py`**: Computer vision algorithms for identifying irregular traffic behavior.
- **`vision/yolo_detector.py`**: Wraps the YOLO object detection model to parse bounding boxes of vehicles in video streams.
- **`vision/weights/best.pt`**: Fine-tuned YOLOv8 weights for specific SIH-related edge detection.

#### `mock data/` Directory
- **`hoshpital.json`, `police.json`, `traffic.json`**: Static GeoJSON seed data files used to populate the database on a fresh install.

#### `scripts/` Directory
- **`generate_pki.sh`**: Helper shell script to generate TLS certificates for testing mTLS (if scaled beyond HiveMQ free tier).

---

## PART 3: Deep-Dive Mechanisms (How Everything Actually Works)

This section strips away the high-level concepts and explains exactly how the code executes the core functions of the project.

### 8. How The Fleet Simulator Works (`simulate_ambulance.py`)
Since we cannot drive 10 real ambulances around a city to test the software, the `simulate_ambulance.py` script acts as a massive "fake world."

1. **Authentication:** The simulator acts like a real dispatcher app. It first sends a POST request to `/auth/login` to get a JWT token so the backend trusts it.
2. **World Loading:** It downloads the entire map from the backend via HTTP (`/map/hospitals` and `/map/traffic-signals`). It now knows where the start and end points are.
3. **Fleet Creation:** It creates a fleet of 12 dummy ambulances. It assigns some to be `MOVING`, some on `STANDBY` at hospitals, and some in a simulated `EMERGENCY` (stuck in traffic).
4. **Route Fetching (OSRM):** For every `MOVING` ambulance, it picks a random intersection as a start, and a random hospital as the destination. It pings the Open Source Routing Machine (OSRM) API to get a "Polyline"—a massive list of GPS coordinates representing the road path.
5. **The Async Loop (The Movement Engine):**
   - Every 2 seconds, the simulator calculates how far the ambulance should have moved based on its speed (e.g., 50 km/h = ~27 meters every 2 seconds).
   - It uses the **Haversine Formula** (a trigonometric formula that calculates the distance between two points on a sphere) to mathematically move the ambulance exactly 27 meters along the OSRM Polyline.
   - It then bundles this new GPS coordinate into a JSON payload and publishes it directly to the MQTT broker on topic `sih/ambulance/telemetry/{ambulance_id}`.
   - The FastAPI backend receives this ping instantly, completely unaware that it was generated by a script rather than a real GPS module.

### 9. How The Edge AI Nodes Work (`edge_node/`)
Instead of sending gigabytes of video to the cloud, the Edge Nodes run tiny AI models locally on microcomputers (like Raspberry Pis or Jetson Nanos) mounted on traffic lights.

1. **Vision (`yolo_detector.py`):** It runs YOLOv8 (You Only Look Once), a neural network trained to draw bounding boxes around cars, trucks, and ambulances in a video frame. If it counts too many cars completely stopped for an extended period, the `anomaly_detection.py` script flags a "Traffic Jam Anomaly" and sends a tiny text alert via MQTT to the backend.
2. **Audio (`siren_classifier.py`):** Video can be blocked by fog or heavy rain. The audio node continuously records 2-second chunks of sound. It converts the audio into a "spectrogram" (a visual picture of frequencies). The AI looks at this picture to see if it perfectly matches the distinct oscillating wave of a wailing ambulance siren. If detected, it immediately sends a "Preemption Trigger" to the backend.

### 10. How The Spatial Math & Preemption Logic Works
When the backend receives a ping that an ambulance is moving, it needs to turn the traffic lights green. But how does it know *which* traffic light? 

1. **Heading Calculation:** When the backend receives coordinates at Time=0s and Time=1s, it uses standard vector mathematics to draw a line between the two points. This line gives the system the ambulance's **Heading Bearing** (e.g., driving 90 degrees East).
2. **PostGIS Distance Filtering:** The system queries the PostgreSQL database using `ST_Distance(location, ambulance_location) < 500`. This instantly filters out all traffic lights in the world, returning only the ones within a 500-meter radius.
3. **The 90-Degree Field of View (FOV):**
   - The backend looks at the 500m radius, but it cannot just turn *all* lights green, or it would turn lights green *behind* the ambulance.
   - It calculates the angle between the ambulance's current bearing and the position of the traffic light.
   - If the traffic light is within a **45-degree angle to the left or right** of the ambulance's forward vector (creating a 90-degree forward cone), it is classified as a "Target Signal."
4. **Triggering:** The backend takes that Target Signal's ID and publishes an MQTT message to `sih/traffic/{target_id}/control` with the payload `{"state": "GREEN"}`. The actual traffic light hardware subscribes to this topic and flips its relay instantly.

### 11. Emergency SOS & Police Dispatch
1. **Trigger:** If the ambulance stops moving for 60 seconds, or the driver hits the SOS button, an incident is created.
2. **Nearest Neighbor Search:** `geospatial.py` runs an `ST_Distance` query against the `PoliceUnit` table, sorting by distance and limiting the result to 1. This guarantees we find the absolute closest patrol car.
3. **Radio Over IP (RoIP):** To notify the police, the system does not expect police to be looking at a web dashboard. `roip_service.py` uses `pyttsx3` (an offline text-to-speech engine) to synthesize an audio file saying: *"Attention Unit 4, emergency assist required at location X."* This audio is sent via Webhooks to a Discord Bot (`discord_bot.py`), which sits in a voice channel acting as a simulated police radio frequency, playing the audio out loud to anyone listening.

---

### 12. Environment & Configuration Reference

#### `.env` File Parameters
The system strictly relies on the following configurations (loaded safely via `app/config.py`):
```env
# Database Settings
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/dbname

# Security
SECRET_KEY=your_secure_random_string_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MQTT Settings
MQTT_BROKER_URL=xyz.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password

# External Integrations
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

#### Execution Commands
- **Start the Core Backend Server:**
  `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Seed the Database with Fake Data:**
  `python seed_db.py`
- **Run the Dummy Fleet Simulator (For Testing):**
  `python simulate_ambulance.py`
- **Start the Mock Police Radio (Discord Gateway):**
  `python discord_gateway/discord_bot.py`
