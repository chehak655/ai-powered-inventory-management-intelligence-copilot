import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.membership import CompanyMember, MemberRole
from app.models.join_request import WorkspaceJoinRequest, JoinRequestStatus
from app.models.audit_log import AuditLog
from app.models.user import User


def test_worker_self_registration_success(client: TestClient, owner_user: dict, db: Session):
    """Test worker successfully submits a join request for an existing workspace."""
    company = owner_user["company"]

    res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Applicant Alice",
            "email": "alice_applicant@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "PENDING"
    assert data["company_id"] == company.id
    assert data["email"] == "alice_applicant@test.com"
    assert data["full_name"] == "Applicant Alice"
    assert "pending approval" in data["message"].lower()

    # Verify user account was created with hashed password
    user = db.query(User).filter(User.email == "alice_applicant@test.com").first()
    assert user is not None
    assert user.hashed_password != "Password123!"

    # Verify NO active company membership was created yet
    member = db.query(CompanyMember).filter(CompanyMember.user_id == user.id).first()
    assert member is None


def test_worker_registration_nonexistent_workspace(client: TestClient):
    """Test worker registration fails cleanly with 404 if workspace does not exist."""
    res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Bob Unknown",
            "email": "bob_unknown@test.com",
            "password": "Password123!",
            "workspace_slug": "totally-nonexistent-workspace-12345",
        },
    )
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"].lower()


def test_duplicate_pending_request_rejected(client: TestClient, owner_user: dict, db: Session):
    """Test that submitting duplicate pending join requests for the same workspace is blocked with 400."""
    company = owner_user["company"]

    # First submission
    res1 = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Charlie Duplicate",
            "email": "charlie_dup@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert res1.status_code == 201

    # Second submission
    res2 = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Charlie Duplicate",
            "email": "charlie_dup@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert res2.status_code == 400
    assert "already pending" in res2.json()["detail"].lower()


def test_existing_member_cannot_submit_join_request(client: TestClient, owner_user: dict, db: Session):
    """Test that an existing member of a workspace cannot submit a join request for the same workspace."""
    company = owner_user["company"]
    headers = owner_user["headers"]

    # Add worker directly
    worker_res = client.post(
        "/api/v1/workspaces/workers",
        headers=headers,
        json={
            "full_name": "Direct Worker",
            "email": "direct_worker@test.com",
            "password": "Password123!",
            "role": "WORKER",
        },
    )
    assert worker_res.status_code == 201

    # Direct worker attempts to submit join request for same company
    res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Direct Worker",
            "email": "direct_worker@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert res.status_code == 400
    assert "already a member" in res.json()["detail"].lower()


def test_direct_owner_created_worker_immediate_login(client: TestClient, owner_user: dict):
    """Path A: Owner directly creates worker who logs in immediately without approval."""
    company = owner_user["company"]
    headers = owner_user["headers"]

    # Owner adds worker
    create_res = client.post(
        "/api/v1/workspaces/workers",
        headers=headers,
        json={
            "full_name": "Instant Worker",
            "email": "instant_worker@test.com",
            "password": "Password123!",
            "role": "WORKER",
        },
    )
    assert create_res.status_code == 201
    assert create_res.json()["role"] == "WORKER"

    # Worker logs in immediately
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "instant_worker@test.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["access_token"] is not None
    assert len(data["companies"]) == 1
    assert data["companies"][0]["role"] == "WORKER"

    worker_token = data["access_token"]

    # Worker accesses workspace details
    ws_res = client.get(
        "/api/v1/workspaces/current",
        headers={"Authorization": f"Bearer {worker_token}", "X-Company-Id": company.id},
    )
    assert ws_res.status_code == 200
    assert ws_res.json()["role"] == "WORKER"

    # Worker is forbidden from owner-only features
    owner_only_res = client.get(
        "/api/v1/workspaces/audit",
        headers={"Authorization": f"Bearer {worker_token}", "X-Company-Id": company.id},
    )
    assert owner_only_res.status_code == 403


def test_pending_worker_login_denied_with_explanation(client: TestClient, owner_user: dict, db: Session):
    """Test that a worker with a pending join request cannot log in and receives a clear 403 message."""
    company = owner_user["company"]

    reg_res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Pending Pete",
            "email": "pete_pending@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert reg_res.status_code == 201

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "pete_pending@test.com", "password": "Password123!"},
    )
    assert login_res.status_code == 403
    assert "pending approval" in login_res.json()["detail"].lower()
    assert company.name.lower() in login_res.json()["detail"].lower()


def test_owner_approval_workflow_end_to_end(client: TestClient, owner_user: dict, db: Session):
    """Test complete Path B workflow: worker submits request, owner reviews & approves, worker logs in."""
    company = owner_user["company"]
    headers = owner_user["headers"]

    # 1. Worker submits request
    submit_res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Sam Student",
            "email": "sam_student@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert submit_res.status_code == 201
    request_id = submit_res.json()["id"]

    # 2. Owner lists pending requests
    list_res = client.get(
        "/api/v1/workspaces/join-requests",
        headers=headers,
    )
    assert list_res.status_code == 200
    requests = list_res.json()
    assert any(r["id"] == request_id and r["status"] == "PENDING" for r in requests)

    # 3. Owner approves request
    approve_res = client.post(
        f"/api/v1/workspaces/join-requests/{request_id}/approve",
        headers=headers,
    )
    assert approve_res.status_code == 200
    approved_data = approve_res.json()
    assert approved_data["status"] == "APPROVED"
    assert approved_data["reviewed_by_id"] is not None

    # Verify audit log
    audit_entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "WORKSPACE_JOIN_REQUEST_APPROVED", AuditLog.resource_id == request_id)
        .first()
    )
    assert audit_entry is not None

    # 4. Repeated approval fails cleanly
    dup_approve = client.post(
        f"/api/v1/workspaces/join-requests/{request_id}/approve",
        headers=headers,
    )
    assert dup_approve.status_code == 400
    assert "already been reviewed" in dup_approve.json()["detail"].lower()

    # 5. Worker can now log in and access workspace
    worker_login = client.post(
        "/api/v1/auth/login",
        json={"email": "sam_student@test.com", "password": "Password123!"},
    )
    assert worker_login.status_code == 200
    worker_data = worker_login.json()
    assert len(worker_data["companies"]) == 1
    assert worker_data["companies"][0]["role"] == "WORKER"
    worker_token = worker_data["access_token"]

    # Worker accesses workspace
    ws_res = client.get(
        "/api/v1/workspaces/current",
        headers={"Authorization": f"Bearer {worker_token}", "X-Company-Id": company.id},
    )
    assert ws_res.status_code == 200


def test_owner_rejection_workflow(client: TestClient, owner_user: dict, db: Session):
    """Test owner rejecting a worker join request with a reason."""
    company = owner_user["company"]
    headers = owner_user["headers"]

    # 1. Worker submits request
    submit_res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Rejected Randy",
            "email": "randy_rejected@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    assert submit_res.status_code == 201
    request_id = submit_res.json()["id"]

    # 2. Owner rejects with reason
    reject_res = client.post(
        f"/api/v1/workspaces/join-requests/{request_id}/reject",
        headers=headers,
        json={"reason": "Role requirements do not match applicant profile."},
    )
    assert reject_res.status_code == 200
    data = reject_res.json()
    assert data["status"] == "REJECTED"
    assert "applicant profile" in data["rejection_reason"]

    # Verify no membership created
    user = db.query(User).filter(User.email == "randy_rejected@test.com").first()
    member = db.query(CompanyMember).filter(CompanyMember.user_id == user.id).first()
    assert member is None

    # 3. Worker login fails with rejection explanation
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "randy_rejected@test.com", "password": "Password123!"},
    )
    assert login_res.status_code == 403
    assert "not approved" in login_res.json()["detail"].lower()


def test_unauthorized_non_owner_approval_forbidden(client: TestClient, owner_user: dict, db: Session):
    """Test that a worker cannot approve join requests."""
    company = owner_user["company"]
    headers = owner_user["headers"]

    # Create worker
    client.post(
        "/api/v1/workspaces/workers",
        headers=headers,
        json={
            "full_name": "Regular Worker",
            "email": "reg_worker@test.com",
            "password": "Password123!",
            "role": "WORKER",
        },
    )
    worker_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reg_worker@test.com", "password": "Password123!"},
    )
    worker_token = worker_login.json()["access_token"]

    # Create applicant request
    sub_res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Target Applicant",
            "email": "target_app@test.com",
            "password": "Password123!",
            "workspace_slug": company.slug,
        },
    )
    req_id = sub_res.json()["id"]

    # Worker tries to list join requests
    list_res = client.get(
        "/api/v1/workspaces/join-requests",
        headers={"Authorization": f"Bearer {worker_token}", "X-Company-Id": company.id},
    )
    assert list_res.status_code == 403

    # Worker tries to approve
    app_res = client.post(
        f"/api/v1/workspaces/join-requests/{req_id}/approve",
        headers={"Authorization": f"Bearer {worker_token}", "X-Company-Id": company.id},
    )
    assert app_res.status_code == 403


def test_cross_workspace_approval_rejected(client: TestClient, owner_user: dict, second_owner: dict, db: Session):
    """Test that an owner of Company A cannot approve join requests belonging to Company B."""
    company_b = second_owner["company"]
    headers_a = owner_user["headers"]

    # Worker requests to join Company Beta
    sub_res = client.post(
        "/api/v1/auth/join-request",
        json={
            "full_name": "Applicant Beta",
            "email": "applicant_beta@test.com",
            "password": "Password123!",
            "workspace_slug": company_b.slug,
        },
    )
    req_id = sub_res.json()["id"]

    # Owner of Company A tries to approve request for Company Beta
    cross_res = client.post(
        f"/api/v1/workspaces/join-requests/{req_id}/approve",
        headers=headers_a,
    )
    assert cross_res.status_code == 404
