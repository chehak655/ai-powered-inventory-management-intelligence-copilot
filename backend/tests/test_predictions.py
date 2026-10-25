import io
import pytest
import pandas as pd
from app.services.ml.orchestrator import run_training_pipeline
from app.models.training import TrainingRun, CandidateModel


def create_regression_csv_bytes(rows=60) -> bytes:
    """Create test regression dataset."""
    records = []
    for i in range(rows):
        records.append({
            "sqft": 1000 + i * 25,
            "bedrooms": (i % 4) + 1,
            "neighborhood": "DOWNTOWN" if i % 2 == 0 else "SUBURBS",
            "price": 200000 + (i * 5000),
        })
    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def trained_regression_model(client, owner_user, db):
    """Fixture that uploads dataset, starts training, runs pipeline, and returns candidate model ID."""
    headers = owner_user["headers"]
    csv_bytes = create_regression_csv_bytes(50)
    upload_resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("houses.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["id"]

    # Configure regression
    cfg_resp = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json={
            "task_type": "regression",
            "target_column": "price",
            "feature_columns": ["sqft", "bedrooms", "neighborhood"],
        },
        headers=headers,
    )
    assert cfg_resp.status_code == 200

    # Start training run
    start_resp = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "regression"},
        headers=headers,
    )
    assert start_resp.status_code == 202
    run_id = start_resp.json()["id"]

    # Run pipeline synchronously for testing
    run_training_pipeline(db, run_id)

    # Get successful candidate model
    model = db.query(CandidateModel).filter(
        CandidateModel.training_run_id == run_id,
        CandidateModel.status == "SUCCESS",
    ).first()
    assert model is not None
    return model.id, dataset_id


def test_model_activation_and_registry(client, owner_user, trained_regression_model):
    """Test listing models in registry, inspecting input schema, and activating candidate model."""
    headers = owner_user["headers"]
    model_id, dataset_id = trained_regression_model

    # 1. List models
    list_resp = client.get(f"/api/v1/models/?dataset_id={dataset_id}", headers=headers)
    assert list_resp.status_code == 200
    models = list_resp.json()
    assert len(models) >= 1

    # 2. Inspect input schema
    schema_resp = client.get(f"/api/v1/models/{model_id}/schema", headers=headers)
    assert schema_resp.status_code == 200
    schema_data = schema_resp.json()
    assert schema_data["model_id"] == model_id
    field_names = [f["name"] for f in schema_data["fields"]]
    assert "sqft" in field_names
    assert "bedrooms" in field_names
    assert "neighborhood" in field_names

    # 3. Activate model
    act_resp = client.post(f"/api/v1/models/{model_id}/activate", headers=headers)
    assert act_resp.status_code == 200
    assert act_resp.json()["is_active"] is True

    # 4. Check active filter
    active_resp = client.get(f"/api/v1/models/?dataset_id={dataset_id}&is_active=true", headers=headers)
    assert active_resp.status_code == 200
    active_list = active_resp.json()
    assert len(active_list) == 1
    assert active_list[0]["id"] == model_id


def test_single_prediction_execution(client, owner_user, trained_regression_model):
    """Test real-time single record prediction endpoint."""
    headers = owner_user["headers"]
    model_id, dataset_id = trained_regression_model

    # Activate model
    client.post(f"/api/v1/models/{model_id}/activate", headers=headers)

    # Predict using model_id
    pred_resp = client.post(
        "/api/v1/predictions/single",
        json={
            "model_id": model_id,
            "inputs": {
                "sqft": 1500,
                "bedrooms": 3,
                "neighborhood": "DOWNTOWN",
            },
        },
        headers=headers,
    )
    assert pred_resp.status_code == 200
    data = pred_resp.json()
    assert data["model_id"] == model_id
    assert data["total_rows"] == 1
    assert data["latency_ms"] >= 0
    assert len(data["predictions"]) == 1
    pred_val = data["predictions"][0]["prediction"]
    assert isinstance(pred_val, (int, float))
    assert pred_val > 0

    # Predict omitting model_id (auto-resolve active model for dataset)
    pred_auto = client.post(
        "/api/v1/predictions/single",
        json={
            "dataset_id": dataset_id,
            "inputs": {
                "sqft": 2000,
                "bedrooms": 4,
                "neighborhood": "SUBURBS",
            },
        },
        headers=headers,
    )
    assert pred_auto.status_code == 200
    assert pred_auto.json()["model_id"] == model_id


def test_batch_prediction_execution(client, owner_user, trained_regression_model):
    """Test batch prediction with JSON records array."""
    headers = owner_user["headers"]
    model_id, _ = trained_regression_model

    records = [
        {"sqft": 1200, "bedrooms": 2, "neighborhood": "DOWNTOWN"},
        {"sqft": 1800, "bedrooms": 3, "neighborhood": "SUBURBS"},
        {"sqft": 2500, "bedrooms": 4, "neighborhood": "DOWNTOWN"},
    ]
    batch_resp = client.post(
        "/api/v1/predictions/batch",
        json={"model_id": model_id, "records": records},
        headers=headers,
    )
    assert batch_resp.status_code == 200
    data = batch_resp.json()
    assert data["total_rows"] == 3
    assert len(data["predictions"]) == 3
    for p in data["predictions"]:
        assert isinstance(p["prediction"], (int, float))


def test_batch_file_prediction_upload(client, owner_user, trained_regression_model):
    """Test uploading a CSV for batch inference and receiving enriched CSV download."""
    headers = owner_user["headers"]
    model_id, _ = trained_regression_model

    test_csv = pd.DataFrame([
        {"sqft": 1100, "bedrooms": 2, "neighborhood": "SUBURBS"},
        {"sqft": 1600, "bedrooms": 3, "neighborhood": "DOWNTOWN"},
    ])
    buf = io.StringIO()
    test_csv.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    file_resp = client.post(
        f"/api/v1/predictions/batch-file?model_id={model_id}",
        files={"file": ("test_input.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert file_resp.status_code == 200
    assert "text/csv" in file_resp.headers["content-type"]
    assert "attachment" in file_resp.headers["content-disposition"]

    # Parse downloaded CSV to verify predicted_value column exists
    res_df = pd.read_csv(io.BytesIO(file_resp.content))
    assert "predicted_value" in res_df.columns
    assert len(res_df) == 2


def test_prediction_history(client, owner_user, trained_regression_model):
    """Test querying prediction history logs."""
    headers = owner_user["headers"]
    model_id, _ = trained_regression_model

    # Run single prediction
    client.post(
        "/api/v1/predictions/single",
        json={"model_id": model_id, "inputs": {"sqft": 1400, "bedrooms": 2, "neighborhood": "SUBURBS"}},
        headers=headers,
    )

    history_resp = client.get("/api/v1/predictions/history", headers=headers)
    assert history_resp.status_code == 200
    logs = history_resp.json()
    assert len(logs) >= 1
    assert logs[0]["model_id"] == model_id
    assert logs[0]["latency_ms"] >= 0


def test_prediction_cross_tenant_isolation(client, owner_user, second_owner, trained_regression_model):
    """Verify Company B cannot access or run predictions with Company A's model."""
    headers_b = second_owner["headers"]
    company_a_model_id, _ = trained_regression_model

    # User B attempts to get model schema
    schema_b = client.get(f"/api/v1/models/{company_a_model_id}/schema", headers=headers_b)
    assert schema_b.status_code == 404

    # User B attempts to predict with Company A's model
    pred_b = client.post(
        "/api/v1/predictions/single",
        json={"model_id": company_a_model_id, "inputs": {"sqft": 1200, "bedrooms": 2, "neighborhood": "SUBURBS"}},
        headers=headers_b,
    )
    assert pred_b.status_code == 404
    assert "Model not found in this company workspace" in pred_b.json()["detail"]
