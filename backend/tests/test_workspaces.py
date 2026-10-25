import pytest
from app.models.membership import MemberRole


def test_owner_adds_worker(client, owner_user):
    payload = {
        "email": "worker1@companyone.com",
        "full_name": "Bob Worker",
        "password": "WorkerPassword123!",
        "role": "WORKER",
    }
    response = client.post(
        "/api/v1/workspaces/workers",
        json=payload,
        headers=owner_user["headers"],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "worker1@companyone.com"
    assert data["role"] == "WORKER"


def test_worker_cannot_add_worker(client, owner_user):
    # First, owner adds a worker
    worker_payload = {
        "email": "subworker@companyone.com",
        "full_name": "Dave Subworker",
        "password": "WorkerPassword123!",
        "role": "WORKER",
    }
    res = client.post(
        "/api/v1/workspaces/workers",
        json=worker_payload,
        headers=owner_user["headers"],
    )
    assert res.status_code == 201

    # Worker logs in
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "subworker@companyone.com", "password": "WorkerPassword123!"},
    )
    worker_token = login_res.json()["access_token"]
    worker_headers = {
        "Authorization": f"Bearer {worker_token}",
        "X-Company-Id": owner_user["company"].id,
    }

    # Worker tries to add another worker -> MUST BE FORBIDDEN
    attempt_res = client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "intruder@companyone.com",
            "full_name": "Intruder Worker",
            "password": "Password123!",
            "role": "WORKER",
        },
        headers=worker_headers,
    )
    assert attempt_res.status_code == 403
    assert "Owner role required" in attempt_res.json()["detail"]


def test_worker_cannot_promote_themselves(client, owner_user):
    # Owner adds worker
    res = client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "ambitious@companyone.com",
            "full_name": "Ambitious Worker",
            "password": "WorkerPassword123!",
            "role": "WORKER",
        },
        headers=owner_user["headers"],
    )
    worker_membership_id = res.json()["id"]

    # Worker logs in
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ambitious@companyone.com", "password": "WorkerPassword123!"},
    )
    worker_token = login_res.json()["access_token"]
    worker_headers = {
        "Authorization": f"Bearer {worker_token}",
        "X-Company-Id": owner_user["company"].id,
    }

    # Worker attempts to update their own role to OWNER -> MUST BE FORBIDDEN
    update_res = client.put(
        f"/api/v1/workspaces/members/{worker_membership_id}/role",
        json={"role": "OWNER"},
        headers=worker_headers,
    )
    assert update_res.status_code == 403
    assert "Owner role required" in update_res.json()["detail"]


def test_owner_can_promote_worker(client, owner_user):
    # Owner adds worker
    res = client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "promotable@companyone.com",
            "full_name": "Promotable Person",
            "password": "WorkerPassword123!",
            "role": "WORKER",
        },
        headers=owner_user["headers"],
    )
    worker_membership_id = res.json()["id"]

    # Owner promotes worker to OWNER
    promote_res = client.put(
        f"/api/v1/workspaces/members/{worker_membership_id}/role",
        json={"role": "OWNER"},
        headers=owner_user["headers"],
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "OWNER"


def test_cannot_demote_last_owner(client, owner_user):
    # Get current members to find owner's membership ID
    members_res = client.get("/api/v1/workspaces/members", headers=owner_user["headers"])
    assert members_res.status_code == 200
    owner_membership = members_res.json()[0]

    # Try to demote sole owner to WORKER
    demote_res = client.put(
        f"/api/v1/workspaces/members/{owner_membership['id']}/role",
        json={"role": "WORKER"},
        headers=owner_user["headers"],
    )
    assert demote_res.status_code == 400
    assert "last owner" in demote_res.json()["detail"].lower()


def test_audit_logs_owner_access_and_worker_denial(client, owner_user):
    # Owner adds worker (generates audit event)
    client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "auditworker@companyone.com",
            "full_name": "Audit Worker",
            "password": "WorkerPassword123!",
            "role": "WORKER",
        },
        headers=owner_user["headers"],
    )

    # Owner views audit logs -> 200 OK
    audit_res = client.get("/api/v1/workspaces/audit", headers=owner_user["headers"])
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 1
    actions = [log["action"] for log in logs]
    assert "WORKSPACE_MEMBER_ADDED" in actions

    # Worker views audit logs -> 403 Forbidden
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "auditworker@companyone.com", "password": "WorkerPassword123!"},
    )
    worker_token = login_res.json()["access_token"]
    worker_headers = {
        "Authorization": f"Bearer {worker_token}",
        "X-Company-Id": owner_user["company"].id,
    }

    forbidden_audit = client.get("/api/v1/workspaces/audit", headers=worker_headers)
    assert forbidden_audit.status_code == 403


def test_add_worker_duplicate_in_same_workspace_fails(client, owner_user):
    payload = {
        "email": "dupe@companyone.com",
        "full_name": "Dupe Worker",
        "password": "WorkerPassword123!",
        "role": "WORKER",
    }
    first_res = client.post(
        "/api/v1/workspaces/workers",
        json=payload,
        headers=owner_user["headers"],
    )
    assert first_res.status_code == 201
    assert first_res.json()["is_active"] is True

    # Attempt to add same email again to same workspace
    second_res = client.post(
        "/api/v1/workspaces/workers",
        json=payload,
        headers=owner_user["headers"],
    )
    assert second_res.status_code == 400
    assert "already a member" in second_res.json()["detail"].lower()


def test_list_members_returns_active_status(client, owner_user):
    members_res = client.get("/api/v1/workspaces/members", headers=owner_user["headers"])
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) >= 1
    for m in members:
        assert "is_active" in m
        assert m["is_active"] is True
        assert "role" in m
        assert "full_name" in m


def test_demote_secondary_owner_succeeds(client, owner_user):
    # Add worker and promote to OWNER
    add_res = client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "coowner@companyone.com",
            "full_name": "Co Owner",
            "password": "WorkerPassword123!",
            "role": "OWNER",
        },
        headers=owner_user["headers"],
    )
    assert add_res.status_code == 201
    coowner_member_id = add_res.json()["id"]

    # Now there are 2 owners in the company. Demoting coowner should succeed.
    demote_res = client.put(
        f"/api/v1/workspaces/members/{coowner_member_id}/role",
        json={"role": "WORKER"},
        headers=owner_user["headers"],
    )
    assert demote_res.status_code == 200
    assert demote_res.json()["role"] == "WORKER"

