"""
app/database.py
───────────────
SQLAlchemy engine, session factory, and the declarative Base.
All ORM models import Base from this module.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# ── Engine & Session ───────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,      # recycle stale connections automatically
    pool_size=10,
    max_overflow=20,
    echo=(settings.app_env == "development"),
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── Declarative Base ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ─────────────────────────────────────────────────────────
def get_db():
    """
    Yield a database session for a single request lifetime.

    Lifecycle:
      - Session is created fresh per request (autocommit=False, autoflush=False).
      - On success: the route function calls db.commit() explicitly.
      - On any unhandled exception: we call db.rollback() here BEFORE close(),
        so the connection is returned to the pool in a clean state.
        Without this, SQLAlchemy's pool issues its own implicit ROLLBACK on
        close(), which can shadow a real commit and cause 'successful 201 but
        nothing persisted' symptoms.
      - db.close() always runs (returns the connection to the pool).
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Startup helper ─────────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Enable the PostGIS extension and create all tables.
    Called once during application startup.

    Prerequisite: the PostgreSQL role used must have CREATE EXTENSION privilege,
    OR the extension must already exist on the target database.

    If PostgreSQL is not reachable at startup the error is logged as a warning
    and the app continues — endpoints that require the DB will return 503 until
    the database becomes available.
    """
    import logging
    _log = logging.getLogger(__name__)

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()

        # Import models so their metadata is registered on Base before create_all
        from app.models import ambulance, police_unit  # noqa: F401

        Base.metadata.create_all(bind=engine)
        _log.info("Database tables verified / created successfully.")

    except Exception as exc:
        _log.warning(
            "⚠️  Could not connect to PostgreSQL at startup: %s\n"
            "    The server will start anyway. DB-backed endpoints will return 503 "
            "until the database is reachable.",
            exc,
        )
