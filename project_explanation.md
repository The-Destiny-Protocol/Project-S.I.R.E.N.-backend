# Intelligent Ambulance Priority & De-Congestion System
**Project Explanation & Architecture Deep Dive**

## The Problem (SIH 2026)
In congested cities, ambulances often get stuck in traffic, leading to delayed emergency response times which can be fatal. The traditional method of sirens is often insufficient for long-distance corridor clearance. 

## The Solution
This project introduces a **Real-Time Priority & De-Congestion System**. It creates a dynamic "Green Corridor" by automatically tracking ambulances, identifying blockages, and instantly dispatching nearby police units over radio to clear the traffic ahead of the ambulance.

---

## 1. Core Components

### A. The IoT Telemetry Pipeline & Redis Cache
Ambulances are equipped with GPS devices that stream their location via **MQTT** to the cloud (HiveMQ). 
- To handle high-frequency scale (1-second intervals from hundreds of vehicles), the backend uses a **Redis Write-Behind Cache**. 
- Telemetry is buffered in Redis (`telemetry_buffer`) and instantly broadcast to the frontend via WebSockets.
- A background task flushes the buffer to PostgreSQL every 5 seconds to prevent database connection exhaustion (`EMAXCONNSESSION`).

### A2. Smart Traffic Light Preemption (Green Corridor)
We implemented a fast-path, sub-millisecond calculation engine for traffic lights directly in the MQTT handler.
- **Directional FOV**: The system calculates the vehicle's heading and uses Haversine math to check if a signal is within 500 meters *and* within a 90-degree forward Field of View.
- **Edge-Triggered Debouncing**: Signals are instantly overridden to `GREEN` upon entry of the FOV cone, and reverted to `NORMAL` the moment the ambulance passes, preventing "ghost states".

### B. AI Vision Anomaly Detection (Edge AI)
Instead of relying solely on the driver to press a panic button, we deployed an Edge AI Vision component (`yolo_detector.py`).
- Using a webcam (simulating a dashcam), the YOLO model detects traffic blockages.
- Upon detecting an anomaly (e.g., severe traffic jam), it automatically fires a `POST /api/v1/emergency/ambulances/{id}/sos` request to the backend.

### C. The Geospatial Engine (PostGIS)
We use **PostgreSQL with the PostGIS extension** to handle all location data.
- When an SOS is triggered, the backend needs to find the *closest* available police unit.
- It uses `ST_Distance` on `Geography` points to calculate the exact distance in meters between the blocked ambulance and all active police units.
- The nearest unit is selected for dispatch.

### D. Emergency Radio Dispatch (RoIP)
Police units coordinate via radio. To automate dispatch without human intervention, we implemented a **Text-To-Speech (TTS) + Radio over IP (RoIP)** pipeline.
- The backend synthesizes a voice alert using offline TTS (`pyttsx3`): *"URGENT. Emergency alert for unit OD-PCR-001. Ambulance is blocked..."*
- This `.wav` file is dispatched over HTTP to a mock RoIP gateway.

### E. Discord Voice Gateway (Mock RoIP)
To demonstrate the radio dispatch in a hackathon setting, we built a standalone **Discord Bot** (`discord_gateway/discord_bot.py`).
- It runs an `aiohttp` web server on port `8001`.
- When the backend sends the audio file, the bot connects to a Discord Voice Channel and broadcasts the alert exactly like a police radio transmission.

### F. Real-Time Command Center Dashboard (WebSockets & GeoJSON)
The control room requires a live map of the city.
- **GeoJSON**: The backend uses PostGIS `ST_AsGeoJSON()` to highly efficiently convert database locations into Mapbox-compatible formats (`/api/v1/map/ambulances`).
- **WebSockets**: Every time an ambulance moves, the MQTT handler broadcasts the new coordinates to all connected React frontends via a WebSocket pool (`/api/v1/ws/live-map`), moving the map markers in real-time.

---

## 2. Technical Workflow (End-to-End)

1. **Movement**: Ambulance IoT sends `{lat, lng, status: "blocked"}` via MQTT.
2. **Buffer & Broadcast**: Backend intercepts the telemetry, saves it to a Redis Hash, and instantly broadcasts it to the Web UI via WebSockets (`/api/v1/ws/live-map`).
3. **Fast-Path Preemption**:
   - Calculates the vehicle heading.
   - If a traffic signal is within 500m and a 90-degree forward arc, it publishes a `GREEN` override to the MQTT hardware.
   - Dispatches a Text-to-Speech (TTS) alert alerting the traffic junction to clear.
4. **Slow-Path Persistence**: A background task flushes the Redis buffer to PostgreSQL every 5 seconds, calculating route deviations and auto-recalculating the path if the ambulance deviated by > 50 meters.
5. **SOS Trigger**: Because the status is `blocked`, the backend finds the nearest police unit using PostGIS `ST_Distance`.
6. **Incident Created**: An `EmergencyIncident` record is saved.
7. **Gateway Dispatch**: A `.wav` file is dispatched over HTTP POST to the Discord Mock Gateway (port 8001).
8. **Radio Broadcast**: Discord Bot joins the voice channel and plays the audio alert to the police officers.
9. **Resolution**: Control room tracks the incident via `GET /incidents/active` and eventually resolves it via `PATCH /incidents/{id}/resolve`.

---

## 3. Deployment (Docker)
The entire backend stack is containerized.
- **FastAPI Backend**: Runs on port `8000`.
- **Discord Gateway**: Runs concurrently on port `8001`.
- Managed seamlessly via `docker-compose.yml`, which handles installing system dependencies like `ffmpeg` (for voice streaming) and `libpq-dev` (for PostGIS).
