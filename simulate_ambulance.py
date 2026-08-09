import json
import time
import math
import random
import asyncio
import requests
import paho.mqtt.client as mqtt

# --- Configuration ---
MQTT_BROKER = "58b2afcd2629461185b24429c78790d6.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "Rohit@sih"
MQTT_PASS = "rohit5460"

API_BASE = "http://localhost:8000/api/v1"

# ANSI Colors
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

# --- Math Helpers ---
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_bearing(lat1, lon1, lat2, lon2):
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi_2)
    x = math.cos(phi_1) * math.sin(phi_2) - math.sin(phi_1) * math.cos(phi_2) * math.cos(delta_lambda)
    theta = math.atan2(y, x)
    return math.degrees(theta)

def move_towards(lat, lon, target_lat, target_lon, distance_m):
    R = 6371000
    bearing = math.radians(get_bearing(lat, lon, target_lat, target_lon))
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_m / R) +
        math.cos(lat_rad) * math.sin(distance_m / R) * math.cos(bearing)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing) * math.sin(distance_m / R) * math.cos(lat_rad),
        math.cos(distance_m / R) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)

# --- OSRM API ---
def fetch_osrm_route(start_lng, start_lat, end_lng, end_lat):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?geometries=geojson"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("code") == "Ok" and data.get("routes"):
            return data["routes"][0]["geometry"]
    except Exception as e:
        print(f"OSRM Fetch Error: {e}")
    return None

class FleetSimulator:
    def __init__(self):
        self.hospitals = []
        self.intersections = []
        self.ambulances = []
        self.jwt_token = None
        
        self.authenticate()
        self.load_world_data()
        self.setup_fleet()
        
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except AttributeError:
            self.client = mqtt.Client()
            
        self.client.tls_set()
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        
        print(f"Connecting to HiveMQ Cloud Broker {MQTT_BROKER}:{MQTT_PORT}...")
        self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.client.loop_start()

    def authenticate(self):
        print("Authenticating Simulator Device...")
        # Create dummy admin if not exists
        try:
            requests.post(f"{API_BASE}/auth/register", json={
                "username": "simulator",
                "password": "password",
                "role": "Admin",
                "is_active": True
            })
        except:
            pass # Ignore if exists
        
        r = requests.post(f"{API_BASE}/auth/login", data={
            "username": "simulator",
            "password": "password"
        })
        r.raise_for_status()
        self.jwt_token = r.json()["access_token"]
        print("✅ Authenticated via REST API")

    def load_world_data(self):
        print("Fetching World Data via APIs...")
        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        
        h_resp = requests.get(f"{API_BASE}/hospitals", headers=headers).json()
        for feature in h_resp.get("features", []):
            coords = feature["geometry"]["coordinates"]
            self.hospitals.append({
                "id": feature["properties"]["id"],
                "name": feature["properties"]["name"],
                "lat": coords[1],
                "lng": coords[0]
            })
            
        t_resp = requests.get(f"{API_BASE}/traffic-signals", headers=headers).json()
        for feature in t_resp.get("features", []):
            coords = feature["geometry"]["coordinates"]
            self.intersections.append({
                "id": feature["properties"]["id"],
                "name": feature["properties"]["name"],
                "lat": coords[1],
                "lng": coords[0]
            })
            
        print(f"Loaded {len(self.hospitals)} Hospitals and {len(self.intersections)} Intersections over HTTP.")

    def setup_fleet(self):
        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        a_resp = requests.get(f"{API_BASE}/map/ambulances", headers=headers).json()
        
        ambs = a_resp.get("features", [])[:12]
        
        for i, feature in enumerate(ambs):
            amb_id = feature["properties"]["id"]
            if i < 5:
                origin = random.choice(self.intersections)
                dest = random.choice(self.hospitals)
                self.ambulances.append({
                    "id": amb_id,
                    "state": "MOVING",
                    "lat": origin["lat"],
                    "lng": origin["lng"],
                    "dest": dest,
                    "speed": random.uniform(40, 60), # km/h
                    "route": None,
                    "route_idx": 0
                })
            elif i < 10:
                base = random.choice(self.hospitals)
                self.ambulances.append({
                    "id": amb_id,
                    "state": "STANDBY",
                    "lat": base["lat"],
                    "lng": base["lng"],
                    "name": base["name"]
                })
            else:
                stuck = random.choice(self.intersections)
                self.ambulances.append({
                    "id": amb_id,
                    "state": "EMERGENCY",
                    "lat": stuck["lat"],
                    "lng": stuck["lng"],
                    "name": stuck["name"]
                })
        print(f"Loaded {len(self.ambulances)} Ambulances to simulate over HTTP.")

    def assign_new_route(self, amb):
        origin = random.choice(self.intersections)
        dest = random.choice(self.hospitals)
        amb["lat"] = origin["lat"]
        amb["lng"] = origin["lng"]
        amb["dest"] = dest
        
        geojson = fetch_osrm_route(origin["lng"], origin["lat"], dest["lng"], dest["lat"])
        if geojson and "coordinates" in geojson:
            amb["route"] = geojson["coordinates"] # List of [lng, lat]
            amb["route_idx"] = 1 # Start moving towards index 1
            
            # Broadcast the new route geometry to MQTT! The backend will save it.
            topic = f"sih/ambulance/route/{amb['id']}"
            self.client.publish(topic, json.dumps(geojson), qos=1)
        else:
            amb["route"] = None # Fallback to Haversine if API fails

    def publish_telemetry(self, amb, status):
        payload = {
            "ambulance_id": amb["id"],
            "operator_type": "GOVT",
            "lat": amb["lat"],
            "lng": amb["lng"],
            "speed": amb.get("speed", 0),
            "status": status
        }
        topic = f"sih/ambulance/telemetry/{amb['id']}"
        self.client.publish(topic, json.dumps(payload), qos=1)

    async def run(self):
        print("Starting Decoupled MQTT Fleet Simulation...")
        print("-" * 60)
        
        # Initialize routes for moving ambulances
        for amb in self.ambulances:
            if amb["state"] == "MOVING":
                self.assign_new_route(amb)
        
        try:
            while True:
                for idx, amb in enumerate(self.ambulances):
                    prefix_id = f"AMB-{idx+1:02d}"
                    
                    if amb["state"] == "MOVING":
                        step_m = (amb["speed"] * 1000 / 3600) * 2 # Distance covered in 2s
                        
                        if amb["route"] and amb["route_idx"] < len(amb["route"]):
                            # Follow polyline
                            target_lng, target_lat = amb["route"][amb["route_idx"]]
                            dist_to_next = haversine_distance(amb["lat"], amb["lng"], target_lat, target_lng)
                            
                            if dist_to_next <= step_m:
                                # Reached node, jump to it and move to next index
                                amb["lat"] = target_lat
                                amb["lng"] = target_lng
                                amb["route_idx"] += 1
                                if amb["route_idx"] >= len(amb["route"]):
                                    self.assign_new_route(amb)
                            else:
                                amb["lat"], amb["lng"] = move_towards(amb["lat"], amb["lng"], target_lat, target_lng, step_m)
                                
                        else:
                            # Fallback if no route or route finished
                            dist_remaining = haversine_distance(amb["lat"], amb["lng"], amb["dest"]["lat"], amb["dest"]["lng"])
                            if dist_remaining <= step_m:
                                self.assign_new_route(amb)
                            else:
                                amb["lat"], amb["lng"] = move_towards(amb["lat"], amb["lng"], amb["dest"]["lat"], amb["dest"]["lng"], step_m)
                        
                        self.publish_telemetry(amb, "active")
                        print(f"{C_GREEN}[EN_ROUTE] {prefix_id}{C_RESET}  -> Lat: {amb['lat']:.4f}, Lng: {amb['lng']:.4f} (Speed: {amb['speed']:.1f} km/h)")
                        
                    elif amb["state"] == "STANDBY":
                        self.publish_telemetry(amb, "active")
                        print(f"{C_YELLOW}[STANDBY]  {prefix_id}{C_RESET}  -> Parked at {amb['name']}")
                        
                    elif amb["state"] == "EMERGENCY":
                        self.publish_telemetry(amb, "blocked")
                        print(f"{C_RED}[CRITICAL] {prefix_id}{C_RESET}  -> Blocked at {amb['name']} (SOS/Corridor Active)")

                print("-" * 60)
                await asyncio.sleep(2)
                
        except KeyboardInterrupt:
            print("\nCaught KeyboardInterrupt! Shutting down fleet simulator cleanly...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("Simulation ended.")

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    sim = FleetSimulator()
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        pass