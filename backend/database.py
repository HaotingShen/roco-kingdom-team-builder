"""Database session management with proper engine configuration.

This module provides a centralized database configuration to avoid
circular imports between main.py and dependencies.py.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.config import DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, ENVIRONMENT

# Engine configuration
engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before use
    echo=False  # Set to True temporarily for debugging SQL queries
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency for database sessions.

    Yields a SQLAlchemy session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
