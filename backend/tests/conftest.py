import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base, get_db
import app.core.database as db_module
import app.models  # Ensure all models are registered to Base.metadata
from app.core.config import settings
from app.main import app
from app.services.auth_service import register_owner
from app.schemas.auth import OwnerRegisterRequest

# Use an in-memory SQLite database with StaticPool for test isolation
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Ensure app's background tasks and service functions use the test engine
db_module.SessionLocal.configure(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def owner_user(db):
    req = OwnerRegisterRequest(
        email="owner1@companyone.com",
        password="SecurePassword123!",
        full_name="Alice Owner",
        company_name="Company One Corp",
    )
    user, company, token = register_owner(db, req)
    return {
        "user": user,
        "company": company,
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Company-Id": company.id,
        },
    }


@pytest.fixture
def second_owner(db):
    req = OwnerRegisterRequest(
        email="owner2@companytwo.com",
        password="SecurePassword123!",
        full_name="Bob Owner",
        company_name="Company Two Ltd",
    )
    user, company, token = register_owner(db, req)
    return {
        "user": user,
        "company": company,
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Company-Id": company.id,
        },
    }
