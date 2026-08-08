import logging
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from app.database import SessionLocal
from app.models.hospital import Hospital
from app.models.traffic import TrafficSignal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_data():
    db: Session = SessionLocal()
    try:
        # Check if hospitals already exist
        if db.query(Hospital).first() is not None:
            logger.info("Database already seeded with hospitals. Skipping.")
        else:
            logger.info("Seeding hospitals...")
            hospitals = [
                Hospital(
                    name="AIIMS Bhubaneswar",
                    geom=WKTElement("POINT(85.7956 20.2359)", srid=4326)
                ),
                Hospital(
                    name="Apollo Hospitals",
                    geom=WKTElement("POINT(85.8285 20.3129)", srid=4326)
                ),
                Hospital(
                    name="KIMS",
                    geom=WKTElement("POINT(85.8184 20.3533)", srid=4326)
                ),
            ]
            db.add_all(hospitals)
            logger.info(f"Added {len(hospitals)} hospitals.")

        # Check if traffic signals already exist
        if db.query(TrafficSignal).first() is not None:
            logger.info("Database already seeded with traffic signals. Skipping.")
        else:
            logger.info("Seeding traffic signals...")
            signals = [
                TrafficSignal(
                    intersection_name="Jayadev Vihar Square",
                    status="AUTO",
                    geom=WKTElement("POINT(85.8163 20.3015)", srid=4326)
                ),
                TrafficSignal(
                    intersection_name="Khandagiri Square",
                    status="AUTO",
                    geom=WKTElement("POINT(85.7865 20.2592)", srid=4326)
                ),
                TrafficSignal(
                    intersection_name="Fire Station Square",
                    status="AUTO",
                    geom=WKTElement("POINT(85.8073 20.2798)", srid=4326)
                ),
                TrafficSignal(
                    intersection_name="Master Canteen Square",
                    status="AUTO",
                    geom=WKTElement("POINT(85.8344 20.2667)", srid=4326)
                ),
                TrafficSignal(
                    intersection_name="Rasulgarh Square",
                    status="AUTO",
                    geom=WKTElement("POINT(85.8569 20.3003)", srid=4326)
                ),
            ]
            db.add_all(signals)
            logger.info(f"Added {len(signals)} traffic signals.")

        db.commit()
        logger.info("Seeding complete.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
