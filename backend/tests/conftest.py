"""
Pytest fixtures for auth testing.

Provides test database session, test client, and helper functions.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from backend.main import app
from backend.models import Base
from backend.database import get_db


# Teach SQLite how to handle PostgreSQL JSONB columns
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# Use in-memory SQLite for tests (faster than PostgreSQL)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Emulate the PostgreSQL functions used in server_default expressions
# (timezone('utc', now())) so INSERTs into users/teams work on SQLite and
# endpoint-level tests can exercise the real auth/team flows.
@event.listens_for(engine, "connect")
def _register_pg_compat_functions(dbapi_connection, _record):
    dbapi_connection.create_function("timezone", 2, lambda _tz, dt: dt)
    dbapi_connection.create_function(
        "now", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with overridden database."""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def guest_user(client):
    """Create a guest user and return tokens."""
    response = client.post("/auth/guest", json={"device_id": "test-device-123"})
    assert response.status_code == 200
    data = response.json()
    return {
        "user": data["user"],
        "access_token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }


@pytest.fixture
def registered_user(client, guest_user):
    """Register a user and return tokens."""
    response = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPass123"
        },
        headers=guest_user["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    return {
        "user": data["user"],
        "access_token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }


@pytest.fixture
def second_guest(client):
    """Create a second guest user for cross-user testing."""
    response = client.post("/auth/guest", json={"device_id": "other-device-456"})
    assert response.status_code == 200
    data = response.json()
    return {
        "user": data["user"],
        "access_token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }
