import json
import time
import requests
import paho.mqtt.client as mqtt

# --- Configuration ---
MQTT_BROKER = "58b2afcd2629461185b24429c78790d6.s1.eu.hivemq.cloud"
MQTT_PORT = 8883  

# Your HiveMQ credentials
MQTT_USER = "Rohit@sih"  
MQTT_PASS = "rohit5460"  

AMBULANCE_ID = "aa9f1cf4-5ab6-4a4b-bd90-98e7ae288ed7"

# --- API Configuration ---
BACKEND_URL = "http://127.0.0.1:8000/api/v1/ambulances/active" # Or /ambulances/active based on your router
# Paste your active JWT token from your React dashboard's Local Storage here!
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODYyMDExOTgsInN1YiI6InJvaGl0In0.gTi2p9FDzk9d33EDSpxa0OL7ZO4YhgF4ZNBy3msYm5M"

def fetch_real_route():
    print(f"🌐 Requesting real route geometry for {AMBULANCE_ID} from backend...")
    headers = {}
    # Just check if the token exists!
    if JWT_TOKEN:
        headers["Authorization"] = f"Bearer {JWT_TOKEN}"

    try:
        response = requests.get(BACKEND_URL, headers=headers)
        
        if response.status_code == 200:
            ambulances = response.json()
            for amb in ambulances:
                if str(amb.get("id")) == AMBULANCE_ID:
                    geojson = amb.get("route_geojson")
                    if geojson and "coordinates" in geojson:
                        coords = geojson["coordinates"]
                        print(f"✅ Successfully loaded {len(coords)} real coordinates from the database!")
                        return coords
            print("⚠️ Ambulance ID not found in active fleet, or route_geojson is empty.")
        elif response.status_code == 401:
            print("❌ 401 Unauthorized: You forgot to paste your JWT_TOKEN into the script!")
        else:
            print(f"❌ Failed to fetch route: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Connection error to FastAPI backend: {e}")
    
    print("⚠️ Falling back to hardcoded test coordinates.")
    return [
        [85.823000, 20.296500], [85.824000, 20.297000], 
        [85.825000, 20.297500], [85.826000, 20.298000]
    ]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Successfully authenticated and connected to HiveMQ Cloud!")
    else:
        print(f"❌ Connection rejected with code {rc}")

def run_simulation():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        client = mqtt.Client()
    
    # Required for HiveMQ Cloud security
    client.tls_set()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    
    print(f"Connecting securely to HiveMQ broker {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    # 1. Fetch the actual route from the database
    real_coordinates = fetch_real_route()
    
    print(f"🚑 Starting autonomous simulation loop for ambulance: {AMBULANCE_ID}")

    try:
        while True:
            # 2. Drive the ambulance along the fetched coordinates
            for coord in real_coordinates:
                # Mapbox GeoJSON is [longitude, latitude]
                lng, lat = coord[0], coord[1]
                
                payload = {
                    "ambulance_id": AMBULANCE_ID,
                    "operator_type": "GOVT",
                    "lat": lat,
                    "lng": lng,
                    "speed": 55.0,
                    "status": "active"
                }
                
                topic = f"sih/ambulance/telemetry/{AMBULANCE_ID}"
                client.publish(f"sih/ambulance/telemetry/{AMBULANCE_ID}", json.dumps(payload))
                
                # print(f"📡 Published telemetry -> Lat: {lat:.4f}, Lng: {lng:.4f}")
                
                time.sleep(1)  # Send update every 1 second
            
            print("🏁 Reached the end of the route! Looping back to the start for continuous demo...")
                
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped by user.")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_simulation()