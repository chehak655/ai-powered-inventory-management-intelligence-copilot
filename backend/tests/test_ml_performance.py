import io
import pytest
import numpy as np
import pandas as pd
import joblib

from app.services.ml.preprocessing import (
    RobustFeaturePreprocessor,
    analyze_target_cardinality,
    split_data,
)
from app.services.ml.evaluator import (
    evaluate_regression,
    evaluate_classification,
    evaluate_anomaly,
    safe_float,
)
from app.services.ml.forecasting import (
    NaiveForecaster,
    SeasonalNaiveForecaster,
    engineer_forecasting_features,
)
from app.services.ml.orchestrator import run_training_pipeline
from app.models.training import CandidateModel, TrainingRun
from app.services.storage import storage_service


def test_imbalanced_classification_performance():
    """Verify macro-F1 and class-balanced models outperform majority-class baseline on imbalanced data."""
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier

    np.random.seed(42)
    n_samples = 400
    # Imbalanced: 90% Class 0 (360), 10% Class 1 (40)
    y = np.array([0] * 360 + [1] * 40)
    # Informative feature with signal
    x1 = np.where(y == 1, np.random.normal(3.0, 1.0, n_samples), np.random.normal(-1.0, 1.0, n_samples))
    x2 = np.random.normal(0, 1.0, n_samples)
    X = np.column_stack([x1, x2])

    # 80/20 train/val split
    indices = np.random.permutation(n_samples)
    train_idx, val_idx = indices[:320], indices[320:]
    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]

    # 1. Dummy baseline
    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(X_train, y_train)
    dummy_preds = dummy.predict(X_val)
    dummy_eval = evaluate_classification(y_val, dummy_preds)
    dummy_f1 = dummy_eval["metrics"]["f1"]

    # 2. Balanced Random Forest
    rf = RandomForestClassifier(n_estimators=50, max_depth=5, class_weight="balanced", random_state=42)
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_val)
    rf_eval = evaluate_classification(
        y_true=y_val,
        y_pred=rf_preds,
        feature_names=["x1", "x2"],
        estimator=rf,
        baseline_metrics=dummy_eval["metrics"],
    )

    # Verifications
    assert rf_eval["metrics"]["accuracy"] > 0.85
    assert rf_eval["metrics"]["macro_f1"] > dummy_f1
    assert rf_eval["baseline_comparison"]["beats_baseline"] is True
    assert rf_eval["confusion_matrix"] is not None
    assert len(rf_eval["confusion_matrix"]["classes"]) == 2
    assert "0" in rf_eval["per_class_summary"]
    assert "1" in rf_eval["per_class_summary"]


def test_regression_informative_vs_noisy_features():
    """Verify regularized regression achieves high R2 on informative data and beats baselines."""
    from sklearn.dummy import DummyRegressor
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import RandomForestRegressor

    np.random.seed(42)
    n = 300
    x_signal = np.linspace(10, 100, n)
    x_noise = np.random.normal(0, 10, n)
    # Target linearly depends on x_signal with small noise
    y = 2.5 * x_signal + np.random.normal(0, 5, n)

    X_train, X_val = np.column_stack([x_signal[:240], x_noise[:240]]), np.column_stack([x_signal[240:], x_noise[240:]])
    y_train, y_val = y[:240], y[240:]

    # Median baseline
    dummy = DummyRegressor(strategy="median")
    dummy.fit(X_train, y_train)
    dummy_preds = dummy.predict(X_val)
    dummy_eval = evaluate_regression(y_val, dummy_preds)

    # Ridge
    ridge = Ridge(alpha=1.0, random_state=42)
    ridge.fit(X_train, y_train)
    ridge_preds = ridge.predict(X_val)
    ridge_eval = evaluate_regression(
        y_true=y_val,
        y_pred=ridge_preds,
        feature_names=["signal", "noise"],
        estimator=ridge,
        baseline_metrics=dummy_eval["metrics"],
    )

    assert ridge_eval["metrics"]["r2"] > 0.85
    assert ridge_eval["metrics"]["mae"] < dummy_eval["metrics"]["mae"]
    assert ridge_eval["baseline_comparison"]["beats_baseline"] is True
    assert ridge_eval["residual_analysis"]["mean_residual"] is not None


def test_time_series_forecasting_no_leakage_and_unscaled_baselines():
    """Verify NaiveForecaster predicts unscaled target and chronological split respects time."""
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    demand = 100.0 + 10.0 * np.sin(np.arange(60) * (2 * np.pi / 7))

    df = pd.DataFrame({"date": dates, "demand": demand})
    train_df, val_df, y_train_s, y_val_s = split_data(df, target_col="demand", task_type="forecasting", val_size=0.25)

    assert len(train_df) == 45
    assert len(val_df) == 15
    # Strict chronological boundary: train dates strictly prior to val dates
    assert train_df["date"].max() < val_df["date"].min()

    y_train = y_train_s.to_numpy()
    y_val = y_val_s.to_numpy()

    forecaster = NaiveForecaster()
    # Fit with dummy X
    X_train_dummy = np.zeros((len(y_train), 2))
    forecaster.fit(X_train_dummy, y_train)

    # Even if X_val is arbitrary scaled numbers, naive forecast must equal raw last value of y_train
    X_val_scaled = np.ones((len(y_val), 2)) * 999.0
    preds = forecaster.predict(X_val_scaled)

    expected_val = float(y_train[-1])
    assert np.allclose(preds, expected_val)
    assert preds[0] > 50.0  # In original demand scale, not 0 to 1


def test_preprocessing_hygiene_and_leakage_prevention():
    """Test currency cleaning, date extraction, identifier dropping, and high-cardinality binning."""
    n = 100
    dates = pd.date_range("2026-01-01", periods=n, freq="D").strftime("%Y-%m-%d").tolist()
    store_types = [f"StoreType_{i % 25}" for i in range(n)]
    df = pd.DataFrame({
        "product_id": [f"PROD_{i}" for i in range(n)],  # Unique ID -> should drop
        "price": [f"${10.0 + (i % 20):.2f}" for i in range(n)],  # Currency -> float
        "launch_date": dates,  # Varied dates -> calendar features
        "constant_col": [42] * n,  # Constant -> should drop
        "store_type": store_types,  # High cardinality (25 unique) -> top cats + Other
        "target": np.random.randint(10, 50, n),
    })

    feature_cols = ["product_id", "price", "launch_date", "constant_col", "store_type"]
    train_df = df.iloc[:80].copy()
    val_df = df.iloc[80:].copy()

    prep = RobustFeaturePreprocessor(top_k_categories=5)
    X_train = prep.fit_transform(train_df, feature_cols)
    X_val = prep.transform(val_df)

    # Identifiers and constant columns dropped
    assert "product_id" in prep.identifier_cols
    assert "constant_col" in prep.constant_cols

    # Currency column converted to numeric
    assert "price" in prep.currency_cols
    assert "price" in prep.final_numeric_cols

    # Date column converted to calendar components
    assert "launch_date" in prep.date_cols
    date_features = [f for f in prep.feature_names_out_ if "launch_date" in f]
    assert len(date_features) > 0

    # High cardinality binning mapped rare categories to 'Other'
    assert "store_type" in prep.high_cardinality_map

    # Matrix shapes valid and finite
    assert X_train.shape[0] == 80
    assert X_val.shape[0] == 20
    assert not np.isnan(X_train).any()
    assert not np.isnan(X_val).any()


def test_metric_edge_cases():
    """Test safety functions on edge cases: zero denominators, constant predictions, non-finite values."""
    # safe_float
    assert safe_float(None) is None
    assert safe_float(float("nan")) is None
    assert safe_float(float("inf")) is None
    assert safe_float(42.123456) == 42.1235

    # Zero denominator WAPE
    y_true = np.array([0.0, 0.0, 0.0])
    y_pred = np.array([0.0, 0.0, 0.0])
    eval_res = evaluate_regression(y_true, y_pred)
    assert eval_res["metrics"]["mae"] == 0.0
    assert eval_res["metrics"]["wape"] is None  # Handled safely

    # Target cardinality analyzer on high cardinality classification
    high_card_target = pd.Series([f"class_{i}" for i in range(50)])
    diag = analyze_target_cardinality(high_card_target, "classification")
    assert diag["is_high_cardinality"] is True
    assert diag["warning"] is not None


def test_end_to_end_model_training_and_safe_promotion(client, db, owner_user):
    """End-to-end integration test of improved ML pipeline and safe model promotion."""
    # Create synthetic dataset with genuine signal
    np.random.seed(42)
    records = []
    for i in range(60):
        stock = i * 3
        lead_time = (i % 5) + 1
        sales = (i % 10) * 4
        # Deterministic demand formula
        demand = 20 + stock * 0.5 + sales * 1.2
        records.append({
            "stock_level": stock,
            "lead_time": lead_time,
            "sales_velocity": sales,
            "unit_price": f"${(15 + (i % 10)):.2f}",
            "demand": round(demand, 2),
        })
    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    # Upload
    headers = owner_user["headers"]
    up_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("perf_inventory.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert up_res.status_code == 201
    dataset_id = up_res.json()["id"]

    # Configure regression
    cfg_res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json={
            "task_type": "regression",
            "target_column": "demand",
            "feature_columns": ["stock_level", "lead_time", "sales_velocity", "unit_price"],
        },
        headers=headers,
    )
    assert cfg_res.status_code == 200

    # Start training
    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "regression"},
        headers=headers,
    )
    assert train_res.status_code == 202
    run_id = train_res.json()["id"]

    # Synchronous execution
    run_training_pipeline(db, run_id)

    # Verify run completed
    run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
    assert run.status == "COMPLETED"

    # Inspect candidate models
    models = db.query(CandidateModel).filter(CandidateModel.training_run_id == run_id).all()
    assert len(models) >= 4

    # Top non-baseline model should achieve high R2 (> 0.8) and outperform baseline
    rf_or_ridge = [m for m in models if m.algorithm in ["linear_regression", "random_forest_regressor", "xgboost_regressor"]]
    assert len(rf_or_ridge) > 0
    best_candidate = min(rf_or_ridge, key=lambda m: m.metrics.get("mae", 999))
    assert best_candidate.metrics["r2"] > 0.80
    assert best_candidate.metrics["mae"] < 10.0

    # Verify safe model promotion
    act_res = client.post(f"/api/v1/models/{best_candidate.id}/activate", headers=headers)
    assert act_res.status_code == 200
    assert act_res.json()["is_active"] is True


def test_cross_company_model_isolation(client, db, owner_user, second_owner):
    """Verify tenant isolation on models endpoint."""
    headers_c1 = owner_user["headers"]
    headers_c2 = second_owner["headers"]

    # Company 1 lists models -> succeeds
    res_c1 = client.get("/api/v1/models/", headers=headers_c1)
    assert res_c1.status_code == 200

    # Company 2 lists models -> only sees company 2 models
    res_c2 = client.get("/api/v1/models/", headers=headers_c2)
    assert res_c2.status_code == 200
    c2_models = res_c2.json()
    for m in c2_models:
        assert m["id"] not in [m1["id"] for m1 in res_c1.json()]


def test_sub_baseline_activation_policy(client, db, owner_user):
    """Verify strict policy prevents activating sub-baseline models without explicit override."""
    headers = owner_user["headers"]
    company_id = owner_user["company"].id

    # Create dummy artifact bundle with estimator
    from sklearn.dummy import DummyRegressor
    buf = io.BytesIO()
    joblib.dump({"estimator": DummyRegressor(), "preprocessor": None}, buf)
    storage_id = storage_service.save_file(
        company_id=company_id,
        content=buf.getvalue(),
        extension=".joblib",
        subfolder="models",
    )

    # Create synthetic candidate model with negative R2
    cand = CandidateModel(
        company_id=company_id,
        training_run_id="dummy_run",
        dataset_id="dummy_dataset",
        algorithm="overfitted_model",
        algorithm_display_name="Overfitted Deep Tree",
        model_family="tree",
        status="SUCCESS",
        metrics={"r2": -0.45, "mae": 99.0},
        evaluation_summary={"baseline_comparison": {"beats_baseline": False}},
        storage_identifier=storage_id,
    )
    db.add(cand)
    db.commit()

    # Attempt activation with strict requirement -> 400
    strict_res = client.post(f"/api/v1/models/{cand.id}/activate?require_beats_baseline=true", headers=headers)
    assert strict_res.status_code == 400
    assert "blocked" in strict_res.json()["detail"].lower()

