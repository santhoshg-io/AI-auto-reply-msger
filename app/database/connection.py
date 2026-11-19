"""Database Connection & Session Factory."""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings
from app.database.models import Base

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")


def get_db():
    """Dependency or context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
