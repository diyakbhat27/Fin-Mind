"""
Shared test fixtures for the Fin Mind backend test suite.
Provides an isolated in-memory SQLite database, pre-seeded users for every role,
and helper functions to generate auth tokens.
"""
import os
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Patch settings BEFORE importing app modules so all components use the test DB
os.environ["DATABASE_URL"] = "sqlite:///./test_finmind.db"

from app.database.session import Base, get_db
from app.models.rbac import User
from app.models.audit import AuditLog
from app.models.config import SystemConfig
from app.models.telemetry import TelemetryLog
from app.auth.security import get_password_hash
from app.auth.jwt import create_access_token
from app.main import app
from app.core.rate_limit import limiter

# Disable rate limiter by default for functional tests
limiter.enabled = False

# ---------------------------------------------------------------------------
# Test database engine & session
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///./test_finmind.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the FastAPI dependency globally for all tests
app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """Create all tables once per test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    # Clean up the test database file
    if os.path.exists("./test_finmind.db"):
        try:
            os.remove("./test_finmind.db")
        except OSError:
            pass


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables and reset rate limit state before each test for isolation."""
    from app.core.rate_limit import auth_backoff_tracker
    auth_backoff_tracker.reset()
    db = TestSessionLocal()
    try:
        db.query(TelemetryLog).delete()
        db.query(AuditLog).delete()
        db.query(SystemConfig).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()

    yield


@pytest.fixture
def db():
    """Provide a test database session."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """Provide a FastAPI TestClient."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Pre-seeded users — one per role
# ---------------------------------------------------------------------------

def _create_user(db_session, username: str, role: str, password: str = "TestPass123", is_active: bool = True) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=f"{username}@finmind.test",
        hashed_password=get_password_hash(password),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def viewer_user(db):
    return _create_user(db, "test_viewer", "VIEWER")

@pytest.fixture
def analyst_user(db):
    return _create_user(db, "test_analyst", "ANALYST")

@pytest.fixture
def admin_user(db):
    return _create_user(db, "test_admin", "ADMIN")

@pytest.fixture
def super_admin_user(db):
    return _create_user(db, "test_super_admin", "SUPER_ADMIN")

@pytest.fixture
def inactive_user(db):
    return _create_user(db, "test_inactive", "VIEWER", is_active=False)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_auth_header(user: User) -> dict:
    """Generate a valid Bearer token header for a given user."""
    token = create_access_token(data={"sub": user.id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(viewer_user):
    return get_auth_header(viewer_user)

@pytest.fixture
def analyst_headers(analyst_user):
    return get_auth_header(analyst_user)

@pytest.fixture
def admin_headers(admin_user):
    return get_auth_header(admin_user)

@pytest.fixture
def super_admin_headers(super_admin_user):
    return get_auth_header(super_admin_user)
