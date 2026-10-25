import uuid
import pytest


def test_cross_workspace_access_denied(client, owner_user, second_owner):
    company_1_id = owner_user["company"].id
    company_2_id = second_owner["company"].id

    # Owner 1 attempts to access Company 2's members using Company 2's ID
    malicious_headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": company_2_id,
    }
    response = client.get("/api/v1/workspaces/members", headers=malicious_headers)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_cross_workspace_worker_creation_denied(client, owner_user, second_owner):
    company_2_id = second_owner["company"].id

    # Owner 1 attempts to add worker into Company 2
    malicious_headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": company_2_id,
    }
    payload = {
        "email": "trojan_worker@companytwo.com",
        "full_name": "Trojan Horse",
        "password": "Password123!",
        "role": "WORKER",
    }
    response = client.post("/api/v1/workspaces/workers", json=payload, headers=malicious_headers)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_cross_workspace_audit_log_access_denied(client, owner_user, second_owner):
    company_2_id = second_owner["company"].id

    # Owner 1 attempts to read Company 2's audit logs
    malicious_headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": company_2_id,
    }
    response = client.get("/api/v1/workspaces/audit", headers=malicious_headers)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_nonexistent_workspace_id_denied(client, owner_user):
    random_uuid = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": random_uuid,
    }
    response = client.get("/api/v1/workspaces/members", headers=headers)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_multi_workspace_user_switching(client, owner_user, second_owner):
    # Owner 2 adds Owner 1 as a worker in Company 2
    add_payload = {
        "email": owner_user["user"].email,
        "full_name": owner_user["user"].full_name,
        "password": "AnyPassword123!",
        "role": "WORKER",
    }
    res = client.post(
        "/api/v1/workspaces/workers",
        json=add_payload,
        headers=second_owner["headers"],
    )
    assert res.status_code == 201

    company_1_id = owner_user["company"].id
    company_2_id = second_owner["company"].id

    # User 1 accesses Company 1 as OWNER
    c1_headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": company_1_id,
    }
    c1_res = client.get("/api/v1/workspaces/current", headers=c1_headers)
    assert c1_res.status_code == 200
    assert c1_res.json()["id"] == company_1_id
    assert c1_res.json()["role"] == "OWNER"

    # User 1 accesses Company 2 as WORKER
    c2_headers = {
        "Authorization": f"Bearer {owner_user['token']}",
        "X-Company-Id": company_2_id,
    }
    c2_res = client.get("/api/v1/workspaces/current", headers=c2_headers)
    assert c2_res.status_code == 200
    assert c2_res.json()["id"] == company_2_id
    assert c2_res.json()["role"] == "WORKER"

    # User 1 cannot perform OWNER operations in Company 2
    worker_try_res = client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "another@companytwo.com",
            "full_name": "Another Guy",
            "password": "Password123!",
            "role": "WORKER",
        },
        headers=c2_headers,
    )
    assert worker_try_res.status_code == 403


def test_ambiguous_workspace_without_header(client, owner_user, second_owner):
    # Add User 1 to Company 2
    client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": owner_user["user"].email,
            "full_name": owner_user["user"].full_name,
            "password": "AnyPassword123!",
            "role": "WORKER",
        },
        headers=second_owner["headers"],
    )

    # When User 1 queries a workspace endpoint WITHOUT X-Company-Id, must receive 400
    headers_without_company = {
        "Authorization": f"Bearer {owner_user['token']}",
    }
    response = client.get("/api/v1/workspaces/current", headers=headers_without_company)
    assert response.status_code == 400
    assert "X-Company-Id header is required" in response.json()["detail"]
