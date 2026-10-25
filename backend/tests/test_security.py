from datetime import timedelta
import jwt
import pytest
from unittest.mock import patch

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.core.config import settings
from app.models.user import User
from app.models.company import Company
from app.schemas.auth import OwnerRegisterRequest
from app.services.auth_service import register_owner


def test_password_hashing_and_verification():
    raw_pass = "MySecretPass_456!"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("IncorrectPass", hashed) is False


def test_password_salting_unique_hashes():
    raw_pass = "IdenticalPassWord123!"
    hash1 = hash_password(raw_pass)
    hash2 = hash_password(raw_pass)

    assert hash1 != hash2
    assert verify_password(raw_pass, hash1) is True
    assert verify_password(raw_pass, hash2) is True


def test_expired_jwt_rejected(client, owner_user):
    # Create an already-expired token (-5 minutes)
    expired_token = create_access_token(
        subject=owner_user["user"].id,
        expires_delta=timedelta(minutes=-5),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_invalid_signature_jwt_rejected(client, owner_user):
    # Encode with wrong secret key
    fake_token = jwt.encode(
        {"sub": owner_user["user"].id},
        "completely-wrong-secret-key-that-does-not-match-settings",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {fake_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_tampered_jwt_rejected(client, owner_user):
    valid_token = owner_user["token"]
    # Tamper with the token string
    tampered_token = valid_token[:-4] + "abcd"
    headers = {"Authorization": f"Bearer {tampered_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401


def test_transaction_rollback_on_registration_failure(db):
    req = OwnerRegisterRequest(
        email="failing_owner@transaction.com",
        password="ValidPassword123!",
        full_name="Atomic Tester",
        company_name="Rollback Inc",
    )

    # Patch Company instantiation or add to simulate failure right after user creation
    with patch("app.services.auth_service.Company", side_effect=RuntimeError("Simulated DB failure")):
        with pytest.raises(Exception):
            register_owner(db, req)

    # Verify that neither user nor company was persisted
    orphaned_user = db.query(User).filter(User.email == "failing_owner@transaction.com").first()
    assert orphaned_user is None

    orphaned_company = db.query(Company).filter(Company.name == "Rollback Inc").first()
    assert orphaned_company is None
