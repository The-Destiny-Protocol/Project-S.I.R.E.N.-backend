import json
import logging
from pathlib import Path
from sqlalchemy import text
from geoalchemy2.elements import WKTElement

from app.database import SessionLocal, init_db
from app.models.police_unit import PoliceUnit
from app.models.hospital import Hospital
from app.models.traffic import TrafficSignal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_DATA_DIR = Path("mock data")

def load_json(filename: str):
    file_path = MOCK_DATA_DIR / filename
    if not file_path.exists():
        logger.warning(f"File {file_path} not found.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def create_point(lat: float, lng: float) -> WKTElement:
    # PostGIS takes (longitude, latitude)
    return WKTElement(f"POINT({lng} {lat})", srid=4326)

def alter_hospital_table(db):
    """
    Ensure the new columns exist in case Base.metadata.create_all() 
    doesn't add them to an already existing 'hospitals' table.
    """
    try:
        db.execute(text("ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS type VARCHAR(50);"))
        db.execute(text("ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS address VARCHAR(500);"))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Could not run ALTER TABLE on hospitals (it may not exist yet or no permissions): {e}")

def seed_police(db):
    data = load_json("police.json")
    count = 0
    for item in data:
        unit_code = item.get("unit_code")
        lat = item.get("lat")
        lng = item.get("lng")
        
        # Check if already exists to prevent duplicates
        existing = db.query(PoliceUnit).filter(PoliceUnit.unit_code == unit_code).first()
        if not existing:
            unit = PoliceUnit(
                unit_code=unit_code,
                location=create_point(lat, lng)
            )
            db.add(unit)
            count += 1
    db.commit()
    logger.info(f"Seeded {count} new Police Units successfully.")

def seed_hospitals(db):
    data = load_json("hoshpital.json")
    count = 0
    for item in data:
        name = item.get("name")
        lat = item.get("lat")
        lng = item.get("lng")
        htype = item.get("type", "")
        address = item.get("address", "")
        
        # Check if already exists by name
        existing = db.query(Hospital).filter(Hospital.name == name).first()
        if not existing:
            hospital = Hospital(
                name=name,
                type=htype,
                address=address,
                geom=create_point(lat, lng)
            )
            db.add(hospital)
            count += 1
    db.commit()
    logger.info(f"Seeded {count} new Hospitals successfully.")

def seed_traffic(db):
    data = load_json("traffic.json")
    count = 0
    for item in data:
        name = item.get("name")
        lat = item.get("lat")
        lng = item.get("lng")
        
        # Check if already exists by intersection_name
        existing = db.query(TrafficSignal).filter(TrafficSignal.intersection_name == name).first()
        if not existing:
            signal = TrafficSignal(
                intersection_name=name,
                geom=create_point(lat, lng)
            )
            db.add(signal)
            count += 1
    db.commit()
    logger.info(f"Seeded {count} new Traffic Intersections successfully.")

def main():
    logger.info("Initializing database and ensuring tables exist...")
    init_db()
    
    db = SessionLocal()
    try:
        alter_hospital_table(db)
        seed_police(db)
        seed_hospitals(db)
        seed_traffic(db)
        logger.info("Database seeding completed successfully.")
    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
