import io
import pytest
import pandas as pd
from fastapi import HTTPException
from app.services.storage import storage_service
from app.models.dataset import Dataset, DatasetConfiguration


def create_sample_csv(rows=50) -> bytes:
    """Create sample CSV bytes with dates, entities, and numeric values."""
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=rows, freq="D").strftime("%Y-%m-%d"),
        "store_id": [f"STORE_{i % 3 + 1}" for i in range(rows)],
        "product_id": [f"SKU_{i % 5 + 1}" for i in range(rows)],
        "demand": [10 + (i * 2) % 30 for i in range(rows)],
        "price": [19.99 + (i % 4) for i in range(rows)],
        "promo": [1 if i % 4 == 0 else 0 for i in range(rows)],
        "constant_flag": [1 for _ in range(rows)],
    })
    # Add a couple duplicate rows to test duplicate detection
    df = pd.concat([df, df.iloc[:3]], ignore_index=True)
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    return csv_buf.getvalue().encode("utf-8")


def create_sample_xlsx(rows=30) -> bytes:
    """Create sample Excel bytes."""
    df = pd.DataFrame({
        "item_id": [f"ITEM_{i}" for i in range(rows)],
        "category": ["Electronics" if i % 2 == 0 else "Home" for i in range(rows)],
        "units_sold": [5 + i for i in range(rows)],
        "revenue": [(5 + i) * 25.0 for i in range(rows)],
    })
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return out.getvalue()


def test_valid_csv_upload_and_profiling(client, owner_user):
    csv_bytes = create_sample_csv(40)
    files = {"file": ("sales_data.csv", csv_bytes, "text/csv")}
    data = {"name": "Q1 Regional Sales"}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        data=data,
        headers=owner_user["headers"],
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["name"] == "Q1 Regional Sales"
    assert res_data["file_format"] == "csv"
    assert res_data["row_count"] > 40
    assert res_data["column_count"] == 7
    assert res_data["profile"] is not None
    assert "columns" in res_data["profile"]
    assert "issues" in res_data["profile"]


def test_valid_xlsx_upload(client, owner_user):
    xlsx_bytes = create_sample_xlsx(25)
    files = {"file": ("inventory.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        headers=owner_user["headers"],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["file_format"] == "xlsx"
    assert data["row_count"] == 25
    assert data["column_count"] == 4


def test_unsupported_file_format_rejected(client, owner_user):
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"
    files = {"file": ("malware.exe", fake_exe, "application/octet-stream")}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        headers=owner_user["headers"],
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_empty_file_rejected(client, owner_user):
    empty_bytes = b""
    files = {"file": ("empty.csv", empty_bytes, "text/csv")}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        headers=owner_user["headers"],
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_malformed_csv_handling(client, owner_user):
    malformed_csv = b"col1,col2\nval1\nval2,extra1,extra2\n"
    files = {"file": ("broken.csv", malformed_csv, "text/csv")}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        headers=owner_user["headers"],
    )
    assert response.status_code == 400
    assert "Failed to parse" in response.json()["detail"]


def test_duplicate_column_names_handled(client, owner_user):
    # CSV with duplicate headers 'price' and 'price'
    csv_content = b"item,price,price\nA,10,12\nB,20,22\nC,30,32\n"
    files = {"file": ("dup_headers.csv", csv_content, "text/csv")}

    response = client.post(
        "/api/v1/datasets/upload",
        files=files,
        headers=owner_user["headers"],
    )
    assert response.status_code == 201
    cols = [c["name"] for c in response.json()["profile"]["columns"]]
    # Duplicate 'price' should be cleanly deduplicated to 'price_1'
    assert "price" in cols
    assert "price_1" in cols


def test_dataset_list_and_pagination(client, owner_user):
    csv_bytes = create_sample_csv(20)
    for i in range(3):
        client.post(
            "/api/v1/datasets/upload",
            files={"file": (f"dataset_{i}.csv", csv_bytes, "text/csv")},
            data={"name": f"Batch Dataset {i}"},
            headers=owner_user["headers"],
        )

    # Page 1, size 2
    res = client.get("/api/v1/datasets/?page=1&page_size=2", headers=owner_user["headers"])
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["total"] >= 3


def test_dataset_preview_pagination(client, owner_user):
    csv_bytes = create_sample_csv(35)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("preview_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    # Request preview page 2 with page_size 10
    preview_res = client.get(
        f"/api/v1/datasets/{dataset_id}/preview?page=2&page_size=10",
        headers=owner_user["headers"],
    )
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["page"] == 2
    assert pdata["page_size"] == 10
    assert len(pdata["records"]) == 10
    assert "columns" in pdata


def test_suggested_configuration(client, owner_user):
    csv_bytes = create_sample_csv(30)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("suggest_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    sugg_res = client.get(
        f"/api/v1/datasets/{dataset_id}/suggested-config",
        headers=owner_user["headers"],
    )
    assert sugg_res.status_code == 200
    sdata = sugg_res.json()
    assert sdata["recommended_task"] in ["forecasting", "regression"]
    assert sdata["target_column"] == "demand"
    assert sdata["date_column"] == "date"
    assert "price" in sdata["feature_columns"]


def test_save_and_retrieve_configuration(client, owner_user):
    csv_bytes = create_sample_csv(30)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("config_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    config_payload = {
        "task_type": "forecasting",
        "target_column": "demand",
        "feature_columns": ["price", "promo"],
        "date_column": "date",
        "entity_columns": ["store_id", "product_id"],
        "excluded_columns": ["constant_flag"],
    }
    save_res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=config_payload,
        headers=owner_user["headers"],
    )
    assert save_res.status_code == 200
    cdata = save_res.json()
    assert cdata["task_type"] == "forecasting"
    assert cdata["target_column"] == "demand"
    assert cdata["configuration_version"] == 1

    # Retrieve configuration
    get_res = client.get(
        f"/api/v1/datasets/{dataset_id}/configuration",
        headers=owner_user["headers"],
    )
    assert get_res.status_code == 200
    assert get_res.json()["target_column"] == "demand"


def test_invalid_configuration_rejected(client, owner_user):
    csv_bytes = create_sample_csv(30)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("invalid_cfg_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    # Nonexistent target column
    bad_payload = {
        "task_type": "regression",
        "target_column": "nonexistent_target_xyz",
        "feature_columns": ["price"],
    }
    bad_res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=bad_payload,
        headers=owner_user["headers"],
    )
    assert bad_res.status_code == 400
    assert "does not exist in the dataset" in bad_res.json()["detail"]


def test_worker_can_upload_and_preview_but_cannot_delete(client, owner_user):
    # Owner adds worker
    client.post(
        "/api/v1/workspaces/workers",
        json={
            "email": "dataworker@companyone.com",
            "full_name": "Data Worker",
            "password": "WorkerPassword123!",
            "role": "WORKER",
        },
        headers=owner_user["headers"],
    )

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "dataworker@companyone.com", "password": "WorkerPassword123!"},
    )
    worker_headers = {
        "Authorization": f"Bearer {login_res.json()['access_token']}",
        "X-Company-Id": owner_user["company"].id,
    }

    # Worker uploads dataset -> Allowed
    csv_bytes = create_sample_csv(20)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("worker_upload.csv", csv_bytes, "text/csv")},
        headers=worker_headers,
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Worker previews dataset -> Allowed
    preview_res = client.get(
        f"/api/v1/datasets/{dataset_id}/preview",
        headers=worker_headers,
    )
    assert preview_res.status_code == 200

    # Worker tries to delete dataset -> FORBIDDEN (Owner only)
    del_res = client.delete(
        f"/api/v1/datasets/{dataset_id}",
        headers=worker_headers,
    )
    assert del_res.status_code == 403
    assert "Owner role required" in del_res.json()["detail"]

    # Owner deletes dataset -> Allowed
    owner_del_res = client.delete(
        f"/api/v1/datasets/{dataset_id}",
        headers=owner_user["headers"],
    )
    assert owner_del_res.status_code == 200


def test_cross_company_dataset_isolation(client, owner_user, second_owner):
    # Owner 1 uploads dataset to Company 1
    csv_bytes = create_sample_csv(20)
    res1 = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("company1_data.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    c1_dataset_id = res1.json()["id"]

    # Owner 2 tries to GET details of Company 1's dataset -> 404
    c2_get_res = client.get(
        f"/api/v1/datasets/{c1_dataset_id}",
        headers=second_owner["headers"],
    )
    assert c2_get_res.status_code == 404

    # Owner 2 tries to PREVIEW Company 1's dataset -> 404
    c2_preview_res = client.get(
        f"/api/v1/datasets/{c1_dataset_id}/preview",
        headers=second_owner["headers"],
    )
    assert c2_preview_res.status_code == 404

    # Owner 2 tries to CONFIGURE Company 1's dataset -> 404
    c2_cfg_res = client.post(
        f"/api/v1/datasets/{c1_dataset_id}/configuration",
        json={"task_type": "regression", "target_column": "demand", "feature_columns": ["price"]},
        headers=second_owner["headers"],
    )
    assert c2_cfg_res.status_code == 404

    # Owner 2 tries to DELETE Company 1's dataset -> 404
    c2_del_res = client.delete(
        f"/api/v1/datasets/{c1_dataset_id}",
        headers=second_owner["headers"],
    )
    assert c2_del_res.status_code == 404


def test_storage_path_traversal_prevention():
    # Attempt directory traversal via storage_service.get_file_path
    with pytest.raises(HTTPException) as excinfo:
        storage_service.get_file_path(
            company_id="company-123",
            storage_identifier="../../../etc/passwd",
        )
    assert excinfo.value.status_code == 400
    assert "path traversal" in excinfo.value.detail.lower()

    # Attempt cross-company access via storage identifier
    with pytest.raises(HTTPException) as excinfo2:
        storage_service.get_file_path(
            company_id="company-123",
            storage_identifier="companies/other-company-456/datasets/secret.csv",
        )
    assert excinfo2.value.status_code == 403
    assert "Access denied" in excinfo2.value.detail
