import io
import time
import pytest
import numpy as np
import pandas as pd
import joblib

from unittest.mock import patch
from app.services.storage import storage_service
from app.services.ml.forecasting import engineer_forecasting_features
from app.services.ml.evaluator import evaluate_regression, evaluate_classification
from app.services.ml.orchestrator import run_training_pipeline
from app.models.training import TrainingRun, CandidateModel


def create_forecasting_csv_bytes(rows=60) -> bytes:
    """Create time-series dataset with 2 stores and 2 products."""
    dates = pd.date_range("2026-01-01", periods=rows // 4, freq="D")
    records = []
    for d in dates:
        for store in ["STORE_A", "STORE_B"]:
            for prod in ["SKU_1", "SKU_2"]:
                base = 20 if prod == "SKU_1" else 50
                records.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "store_id": store,
                    "product_id": prod,
                    "demand": base + np.random.randint(0, 15),
                    "price": 19.99 if prod == "SKU_1" else 39.99,
                    "promotion": np.random.choice([0, 1]),
                })
    df = pd.DataFrame(records).sort_values("date")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def create_classification_csv_bytes(rows=60) -> bytes:
    """Create classification dataset with stockout risk classes."""
    records = []
    for i in range(rows):
        stock = i * 2
        lead_time = (i % 7) + 1
        risk = "HIGH" if (stock < 20 and lead_time > 3) else "LOW"
        records.append({
            "current_stock": stock,
            "lead_time_days": lead_time,
            "daily_velocity": (i % 5) + 1.5,
            "stockout_risk": risk,
        })
    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def test_grouped_lag_features_no_cross_entity_leakage():
    """Verify group-aware lag features prevent one product's demand from leaking into another."""
    df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"],
        "product_id": ["PROD_A", "PROD_A", "PROD_B", "PROD_B"],
        "demand": [100.0, 110.0, 5.0, 8.0],
    })
    feat_df, cols, _ = engineer_forecasting_features(
        df=df,
        date_col="date",
        target_col="demand",
        entity_cols=["product_id"],
    )

    # For PROD_B on day 2, lag_1 MUST be 5.0 (PROD_B day 1), NOT 110.0 or 100.0 (PROD_A)!
    prod_b_day2 = feat_df[(feat_df["product_id"] == "PROD_B") & (feat_df["date"] == "2026-01-02")].iloc[0]
    assert prod_b_day2["lag_1"] == 5.0


def test_regression_and_forecasting_training_pipeline(client, db, owner_user):
    csv_bytes = create_forecasting_csv_bytes(60)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("demand_forecast.csv", csv_bytes, "text/csv")},
        data={"name": "Retail Demand Log"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Save forecasting configuration
    cfg_res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json={
            "task_type": "forecasting",
            "target_column": "demand",
            "feature_columns": ["price", "promotion"],
            "date_column": "date",
            "entity_columns": ["store_id", "product_id"],
        },
        headers=owner_user["headers"],
    )
    assert cfg_res.status_code == 200

    # Start training run
    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "forecasting"},
        headers=owner_user["headers"],
    )
    assert train_res.status_code == 202
    run_id = train_res.json()["id"]

    # Synchronously execute training pipeline for the test
    run_training_pipeline(db, run_id)

    # Inspect completed training run
    get_res = client.get(f"/api/v1/training/runs/{run_id}", headers=owner_user["headers"])
    assert get_res.status_code == 200
    rdata = get_res.json()
    assert rdata["status"] in ["COMPLETED", "PARTIALLY_FAILED"]
    assert len(rdata["models"]) >= 3
    assert rdata["val_row_count"] > 0
    assert rdata["duration_seconds"] > 0

    # Verify comparison endpoint
    comp_res = client.get(f"/api/v1/training/runs/{run_id}/comparison", headers=owner_user["headers"])
    assert comp_res.status_code == 200
    cdata = comp_res.json()
    assert cdata["primary_metric"] == "rmse"
    assert len(cdata["metrics_table"]) >= 3

    # Check top model metrics
    best_model = cdata["metrics_table"][0]
    assert best_model["status"] == "SUCCESS"
    assert "rmse" in best_model["metrics"]
    assert "mae" in best_model["metrics"]


def test_classification_training_pipeline(client, db, owner_user):
    csv_bytes = create_classification_csv_bytes(50)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("stockout_risk.csv", csv_bytes, "text/csv")},
        data={"name": "Stockout Classification"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Configure classification
    cfg_res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json={
            "task_type": "classification",
            "target_column": "stockout_risk",
            "feature_columns": ["current_stock", "lead_time_days", "daily_velocity"],
        },
        headers=owner_user["headers"],
    )
    assert cfg_res.status_code == 200

    # Start training
    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "classification"},
        headers=owner_user["headers"],
    )
    assert train_res.status_code == 202
    run_id = train_res.json()["id"]

    # Execute
    run_training_pipeline(db, run_id)

    # Check models
    get_res = client.get(f"/api/v1/training/runs/{run_id}", headers=owner_user["headers"])
    assert get_res.status_code == 200
    models = get_res.json()["models"]
    assert len(models) >= 3

    for m in models:
        if m["status"] == "SUCCESS":
            assert "accuracy" in m["metrics"]
            assert "f1" in m["metrics"]


def test_model_artifact_save_and_load(client, db, owner_user):
    csv_bytes = create_classification_csv_bytes(40)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("artifact_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "classification"},
        headers=owner_user["headers"],
    )
    run_id = train_res.json()["id"]
    run_training_pipeline(db, run_id)

    # Find successful candidate model
    cand = db.query(CandidateModel).filter(
        CandidateModel.training_run_id == run_id,
        CandidateModel.status == "SUCCESS"
    ).first()
    assert cand is not None
    assert cand.storage_identifier is not None

    # Load artifact bytes using storage_service
    artifact_bytes = storage_service.read_file(owner_user["company"].id, cand.storage_identifier)
    bundle = joblib.load(io.BytesIO(artifact_bytes))

    assert "estimator" in bundle
    assert "preprocessor" in bundle
    assert "feature_names" in bundle
    assert bundle["task_type"] == "classification"


def test_partial_candidate_failure_resilience(client, db, owner_user):
    csv_bytes = create_classification_csv_bytes(40)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("partial_fail.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "classification"},
        headers=owner_user["headers"],
    )
    run_id = train_res.json()["id"]

    # Mock LogisticRegression.fit to simulate failure in one candidate model
    with patch("sklearn.linear_model.LogisticRegression.fit", side_effect=RuntimeError("Simulated algorithm crash")):
        run_training_pipeline(db, run_id)

    run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
    assert run.status == "PARTIALLY_FAILED"

    # Other models like DummyClassifier and RandomForestClassifier must have succeeded!
    models = db.query(CandidateModel).filter(CandidateModel.training_run_id == run_id).all()
    statuses = {m.algorithm: m.status for m in models}
    assert statuses.get("logistic_regression") == "FAILED"
    assert statuses.get("dummy_classifier") == "SUCCESS"
    assert statuses.get("random_forest_classifier") == "SUCCESS"


def test_cross_company_training_isolation(client, db, owner_user, second_owner):
    csv_bytes = create_forecasting_csv_bytes(40)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("c1_train.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "forecasting"},
        headers=owner_user["headers"],
    )
    run_id = train_res.json()["id"]
    run_training_pipeline(db, run_id)

    # Company 2 tries to GET Company 1's training run -> 404
    c2_run_res = client.get(f"/api/v1/training/runs/{run_id}", headers=second_owner["headers"])
    assert c2_run_res.status_code == 404

    # Company 2 tries to GET Company 1's model comparison -> 404
    c2_comp_res = client.get(f"/api/v1/training/runs/{run_id}/comparison", headers=second_owner["headers"])
    assert c2_comp_res.status_code == 404


def test_duplicate_concurrent_run_conflict(client, db, owner_user):
    csv_bytes = create_classification_csv_bytes(30)
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("concurrent_test.csv", csv_bytes, "text/csv")},
        headers=owner_user["headers"],
    )
    dataset_id = upload_res.json()["id"]

    # First run created with mocked execution so it remains QUEUED/RUNNING
    with patch("app.api.v1.training.run_training_pipeline"):
        train_res1 = client.post(
            "/api/v1/training/start",
            json={"dataset_id": dataset_id, "task_type": "classification"},
            headers=owner_user["headers"],
        )
        assert train_res1.status_code == 202

        # Second immediate run on same dataset -> 409 Conflict
        train_res2 = client.post(
            "/api/v1/training/start",
            json={"dataset_id": dataset_id, "task_type": "classification"},
            headers=owner_user["headers"],
        )
        assert train_res2.status_code == 409
        assert "already in progress" in train_res2.json()["detail"].lower()
