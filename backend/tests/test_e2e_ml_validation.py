import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.services.dataset_service import validate_dataset_configuration
from app.services.ml.forecasting import (
    NaiveForecaster,
    SeasonalNaiveForecaster,
    engineer_forecasting_features,
)
from app.services.ml.preprocessing import split_data, RobustFeaturePreprocessor
from app.services.ml.evaluator import evaluate_regression, evaluate_classification


def test_dataset_config_validation_high_cardinality_and_recommendation():
    """
    Test dataset configuration validation:
    - Flags high cardinality and continuous targets when classification is selected.
    - Recommends regression for continuous numeric quantities.
    - Computes class counts and estimated validation-set support.
    - Never mutates the user's selected task or target.
    """
    # 990 rows with 91 distinct numeric values (like Grocery dataset Stock_Quantity)
    stock_values = np.random.randint(10, 101, size=990)
    df = pd.DataFrame({
        "Stock_Quantity": stock_values,
        "Price": np.random.uniform(5.0, 50.0, size=990),
        "Category": np.random.choice(["Bakery", "Produce", "Dairy"], size=990),
    })

    profile = {
        "summary": {"row_count": 990, "column_count": 3},
        "columns": [
            {"name": "Stock_Quantity", "inferred_type": "numeric", "unique_count": 91},
            {"name": "Price", "inferred_type": "numeric", "unique_count": 800},
            {"name": "Category", "inferred_type": "categorical", "unique_count": 3},
        ],
    }

    # User explicitly selects classification on numeric Stock_Quantity
    val_res = validate_dataset_configuration(
        profile=profile,
        task_type="classification",
        target_column="Stock_Quantity",
        feature_columns=["Price", "Category"],
        df=df,
    )

    # Validates warnings and recommendation
    assert val_res["is_valid"] is True
    assert len(val_res["warnings"]) >= 1
    assert any("continuous or high cardinality" in w for w in val_res["warnings"])
    assert val_res["recommendation"] is not None
    assert "regression" in val_res["recommendation"].lower()

    # Diagnostics computed
    diag = val_res["target_diagnostics"]
    assert diag["unique_classes"] >= 50
    assert diag["is_high_cardinality"] is True
    assert diag["estimated_val_support_per_class"] > 0
    # Holdout has ~198 rows across ~91 classes -> ~2.18 examples per class
    assert diag["estimated_val_support_per_class"] < 5.0


def test_dataset_config_validation_incompatible_regression_target():
    """Test warning when categorical text target is selected for regression/forecasting."""
    profile = {
        "summary": {"row_count": 100, "column_count": 2},
        "columns": [
            {"name": "Product_Status", "inferred_type": "categorical", "unique_count": 3},
            {"name": "Feature_1", "inferred_type": "numeric", "unique_count": 80},
        ],
    }

    val_res = validate_dataset_configuration(
        profile=profile,
        task_type="regression",
        target_column="Product_Status",
        feature_columns=["Feature_1"],
    )

    assert len(val_res["warnings"]) >= 1
    assert any("categorical text" in w for w in val_res["warnings"])


def test_forecasting_chronological_ordering_and_holdout():
    """
    Test time-series forecasting chronological partitioning:
    - Every training observation must strictly precede all validation observations.
    - Future holdout is genuine (no past/future interleaving).
    """
    base_date = datetime(2025, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(100)]
    df = pd.DataFrame({
        "Date": dates,
        "Demand": np.sin(np.linspace(0, 10, 100)) + 10.0,
        "Store": ["Store_A"] * 100,
    })

    feat_df, gen_features, _ = engineer_forecasting_features(
        df=df,
        date_col="Date",
        target_col="Demand",
        entity_cols=["Store"],
    )

    train_df, val_df, y_train, y_val = split_data(
        df=feat_df,
        target_col="Demand",
        task_type="forecasting",
        val_size=0.25,
        date_col="Date",
    )

    assert len(train_df) > 0
    assert len(val_df) > 0
    assert train_df["Date"].max() < val_df["Date"].min(), "Training dates must be strictly earlier than validation dates"


def test_forecasting_entity_boundary_isolation():
    """
    Test that lag and rolling features do NOT leak across entity boundaries (e.g. SKU / Store).
    Store_B's initial lag must not equal Store_A's final demand.
    """
    base_date = datetime(2025, 1, 1)
    # Store A has high demand 1000, Store B has low demand 10
    dates_a = [base_date + timedelta(days=i) for i in range(30)]
    dates_b = [base_date + timedelta(days=i) for i in range(30)]

    df = pd.DataFrame({
        "Date": dates_a + dates_b,
        "Store": ["Store_A"] * 30 + ["Store_B"] * 30,
        "Demand": [1000.0] * 30 + [10.0] * 30,
    })

    feat_df, _, _ = engineer_forecasting_features(
        df=df,
        date_col="Date",
        target_col="Demand",
        entity_cols=["Store"],
    )

    store_b_rows = feat_df[feat_df["Store"] == "Store_B"].sort_values(by="Date").reset_index(drop=True)
    # Store B's first lag_1 must NOT bleed from Store A (which had 1000.0). It must be 0.0 or Store B's own value.
    assert store_b_rows.iloc[0]["lag_1"] == 0.0, "Entity boundary violated: Store B saw Store A's past demand"
    assert store_b_rows.iloc[0]["rolling_mean_7"] == 0.0


def test_forecasting_leakage_prevention_on_future_targets():
    """
    Test that modifying future validation target values has zero impact on past features.
    """
    base_date = datetime(2025, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(50)]
    demands_original = [float(i + 1) for i in range(50)]

    df1 = pd.DataFrame({
        "Date": dates,
        "Demand": demands_original,
    })

    feat_df1, _, _ = engineer_forecasting_features(
        df=df1,
        date_col="Date",
        target_col="Demand",
    )

    # Now tamper with future targets (last 10 days) drastically
    demands_tampered = list(demands_original[:40]) + [999999.0] * 10
    df2 = pd.DataFrame({
        "Date": dates,
        "Demand": demands_tampered,
    })

    feat_df2, _, _ = engineer_forecasting_features(
        df=df2,
        date_col="Date",
        target_col="Demand",
    )

    # Features for the first 40 days must be 100% identical
    for col in ["lag_1", "lag_2", "rolling_mean_7"]:
        np.testing.assert_array_almost_equal(
            feat_df1.iloc[:40][col].values,
            feat_df2.iloc[:40][col].values,
            err_msg=f"Feature {col} changed in training window when future targets were modified (leakage!)",
        )


def test_forecasting_naive_and_seasonal_baselines():
    """
    Test naive and seasonal naive forecasting baselines operate strictly on training history.
    """
    y_train = np.array([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
    X_train = np.zeros((len(y_train), 2))
    X_val = np.zeros((5, 2))

    # Naive Forecaster
    naive = NaiveForecaster()
    naive.fit(X_train, y_train)
    naive_preds = naive.predict(X_val)
    assert len(naive_preds) == 5
    assert (naive_preds == 24.0).all(), "Naive forecaster must predict the last observed training value"

    # Seasonal Naive Forecaster (season_length=7)
    s_naive = SeasonalNaiveForecaster(season_length=7)
    s_naive.fit(X_train, y_train)
    s_preds = s_naive.predict(X_val)
    assert len(s_preds) == 5
    # Last 7 values of y_train: [12, 14, 16, 18, 20, 22, 24]
    assert s_preds[0] == 12.0
    assert s_preds[1] == 14.0
    assert s_preds[4] == 20.0


def test_baseline_comparison_absolute_and_percentage_improvement():
    """
    Test baseline-first evaluation computes both absolute and percentage improvement.
    """
    y_true = np.array([100.0, 110.0, 105.0, 95.0, 100.0])
    # Baseline predictions (RMSE ~6.32)
    y_pred_cand = np.array([101.0, 108.0, 104.0, 96.0, 101.0])
    baseline_metrics = {"rmse": 10.0, "mae": 8.0}

    res = evaluate_regression(
        y_true=y_true,
        y_pred=y_pred_cand,
        baseline_metrics=baseline_metrics,
        primary_metric="rmse",
    )

    base_comp = res["baseline_comparison"]
    assert base_comp["beats_baseline"] is True
    assert base_comp["absolute_improvement"] > 0
    assert base_comp["improvement_pct"] > 0
    # Candidate RMSE is ~1.73 -> improvement is 10.0 - 1.73 = 8.27 (> 80% improvement)
    assert base_comp["improvement_pct"] > 80.0


def test_underperforming_candidate_identification():
    """
    Test that candidate models with worse error than the baseline are explicitly flagged.
    """
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred_poor = np.array([50.0, 50.0, 50.0, 50.0])  # Huge error
    baseline_metrics = {"rmse": 5.0, "mae": 4.0}

    res = evaluate_regression(
        y_true=y_true,
        y_pred=y_pred_poor,
        baseline_metrics=baseline_metrics,
        primary_metric="rmse",
    )

    base_comp = res["baseline_comparison"]
    assert base_comp["beats_baseline"] is False
    assert base_comp["absolute_improvement"] < 0
    assert base_comp["improvement_pct"] < 0
