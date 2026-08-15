import os
import sys

# Add the project root to the path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.models.incident import EmergencyIncident
from app.models.ambulance import Ambulance

def clean_database():
    db = SessionLocal()
    try:
        # Delete all records from the emergency_incidents table
        deleted_incidents = db.query(EmergencyIncident).delete()
        
        # Update ambulances stuck in SOS_ACTIVE state
        updated_ambulances = db.query(Ambulance).filter(Ambulance.status == 'SOS_ACTIVE').update({"status": "active"})
        
        db.commit()
        print(f"SUCCESS: Deleted {deleted_incidents} emergency incidents.")
        print(f"SUCCESS: Reset {updated_ambulances} ambulances to 'active' status.")
    except Exception as e:
        db.rollback()
        print(f"ERROR cleaning database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_database()
