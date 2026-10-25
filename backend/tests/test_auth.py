import pytest
from app.models.user import User


def test_successful_owner_registration(client, db):
    payload = {
        "email": "newowner@enterprise.com",
        "password": "Password123!",
        "full_name": "Carol Danvers",
        "company_name": "Starforce Logistics",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "newowner@enterprise.com"
    assert data["user"]["full_name"] == "Carol Danvers"
    assert len(data["companies"]) == 1
    assert data["companies"][0]["name"] == "Starforce Logistics"
    assert data["companies"][0]["role"] == "OWNER"


def test_duplicate_registration_fails(client, owner_user):
    payload = {
        "email": "owner1@companyone.com",  # Already registered
        "password": "Password123!",
        "full_name": "Clone Alice",
        "company_name": "Duplicate Corp",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_successful_login(client, owner_user):
    payload = {
        "email": "owner1@companyone.com",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "owner1@companyone.com"
    assert len(data["companies"]) == 1
    assert data["companies"][0]["id"] == owner_user["company"].id


def test_login_invalid_password(client, owner_user):
    payload = {
        "email": "owner1@companyone.com",
        "password": "WrongPassword999!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_nonexistent_email(client):
    payload = {
        "email": "doesnotexist@unknown.com",
        "password": "SomePassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_get_current_user_me(client, owner_user):
    response = client.get("/api/v1/auth/me", headers=owner_user["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "owner1@companyone.com"
    assert len(data["companies"]) >= 1


def test_get_me_unauthorized_without_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_deactivated_user_access_denied(client, db, owner_user):
    # Deactivate the user
    user = db.query(User).filter(User.id == owner_user["user"].id).first()
    user.is_active = False
    db.commit()

    response = client.get("/api/v1/auth/me", headers=owner_user["headers"])
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()


def test_logout_endpoint(client, owner_user):
    response = client.post("/api/v1/auth/logout", headers=owner_user["headers"])
    assert response.status_code == 200
    assert "Logged out successfully" in response.json()["message"]
