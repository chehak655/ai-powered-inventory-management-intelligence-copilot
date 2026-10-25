import pytest
import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import IsolationForest

from app.services.ml.evaluator import (
    evaluate_regression,
    evaluate_classification,
    evaluate_anomaly,
    safe_float,
)


# ==============================================================================
# 1. ACCURACY AND F1 CALCULATIONS ON KNOWN PREDICTIONS
# ==============================================================================

def test_accuracy_and_f1_known_predictions():
    # 4 samples: 3 correct, 1 wrong
    y_true = np.array(["cat", "dog", "cat", "dog"])
    y_pred = np.array(["cat", "dog", "dog", "dog"])  # sample 2 is wrong (true: cat, pred: dog)

    res = evaluate_classification(y_true, y_pred)
    metrics = res["metrics"]

    # Accuracy: 3 / 4 = 0.75
    assert metrics["accuracy"] == 0.75

    # Cat: TP=1, FP=0, FN=1 -> Prec=1.0, Rec=0.5 -> F1 = 2*(1*0.5)/(1+0.5) = 2/3 = 0.6667
    # Dog: TP=2, FP=1, FN=0 -> Prec=2/3 = 0.6667, Rec=1.0 -> F1 = 2*(2/3 * 1)/(2/3 + 1) = 0.8
    # Macro F1 = (2/3 + 0.8) / 2 = (0.66667 + 0.8) / 2 = 0.7333
    assert metrics["macro_f1"] == 0.7333
    assert metrics["f1"] == 0.7333

    # Weighted F1: (2 * 0.66667 + 2 * 0.8) / 4 = 0.7333 (balanced here)
    assert metrics["weighted_f1"] == 0.7333


# ==============================================================================
# 2. IMBALANCED CLASSIFICATION AND CONFUSION MATRICES
# ==============================================================================

def test_imbalanced_classification_and_confusion_matrices():
    # 90 majority ("Normal") and 10 minority ("Fraud")
    y_true = np.array(["Normal"] * 90 + ["Fraud"] * 10)
    # Most frequent baseline predicts "Normal" for everything
    y_pred = np.array(["Normal"] * 100)

    res = evaluate_classification(y_true, y_pred)
    metrics = res["metrics"]

    # High accuracy (90%) but severe failure on minority class
    assert metrics["accuracy"] == 0.9
    # Macro-F1 heavily penalizes 0% recall on Fraud
    # Normal: TP=90, FP=10, FN=0 -> Prec=0.9, Rec=1.0 -> F1 = 2*0.9/1.9 = 0.9474
    # Fraud: TP=0, FP=0, FN=10 -> Prec=0, Rec=0 -> F1 = 0
    # Macro F1 = 0.9474 / 2 = 0.4737
    assert metrics["macro_f1"] == 0.4737
    # Distinct from weighted F1: 0.9 * 0.9474 = 0.8526
    assert metrics["weighted_f1"] == 0.8526
    assert metrics["macro_f1"] != metrics["weighted_f1"]

    # Confusion matrix structure
    cm = res["confusion_matrix"]
    assert cm is not None
    assert set(cm["classes"]) == {"Fraud", "Normal"}
    matrix = np.array(cm["matrix"])
    assert np.sum(matrix) == 100
    assert np.trace(matrix) == 90  # 90 correct predictions

    # Per-class summary
    pcs = res["per_class_summary"]
    assert pcs["Fraud"]["support"] == 10
    assert pcs["Fraud"]["f1"] == 0.0
    assert pcs["Normal"]["support"] == 90
    assert pcs["Normal"]["recall"] == 1.0


# ==============================================================================
# 3. ROC-AUC EDGE CASES
# ==============================================================================

def test_roc_auc_binary_string_labels_not_inverted():
    # Binary classification with string labels: "Low" (negative) and "High" (positive)
    y_true = np.array(["Low", "High", "Low", "High"])
    # Perfect probabilities for "High" (index 1)
    y_prob = np.array([
        [0.85, 0.15],
        [0.10, 0.90],
        [0.90, 0.10],
        [0.05, 0.95],
    ])
    classes = np.array(["Low", "High"])

    res = evaluate_classification(
        y_true=y_true,
        y_pred=np.array(["Low", "High", "Low", "High"]),
        y_prob=y_prob,
        classes=classes,
    )
    # Perfect separation must give 1.0, NEVER 0.0 or inverted score
    assert res["metrics"]["roc_auc"] == 1.0


def test_roc_auc_multiclass_missing_validation_class():
    # 3 classes in training: A, B, C
    # But in validation, only A and B appear
    y_true = np.array(["A", "B", "A", "B"])
    y_prob = np.array([
        [0.8, 0.1, 0.1],
        [0.1, 0.8, 0.1],
        [0.7, 0.2, 0.1],
        [0.2, 0.7, 0.1],
    ])
    classes = np.array(["A", "B", "C"])

    res = evaluate_classification(
        y_true=y_true,
        y_pred=np.array(["A", "B", "A", "B"]),
        y_prob=y_prob,
        classes=classes,
    )
    # Must compute ROC-AUC across evaluatable classes without crashing
    assert res["metrics"]["roc_auc"] == 1.0


def test_roc_auc_single_class_validation_partition():
    # Only 1 class present in validation partition
    y_true = np.array(["A", "A", "A"])
    y_prob = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3]])
    classes = np.array(["A", "B"])

    res = evaluate_classification(
        y_true=y_true,
        y_pred=np.array(["A", "A", "A"]),
        y_prob=y_prob,
        classes=classes,
    )
    # Safely returns None since ROC-AUC is undefined with a single class
    assert res["metrics"]["roc_auc"] is None


# ==============================================================================
# 4. REGRESSION METRICS AND INVERSE TRANSFORMATIONS
# ==============================================================================

def test_regression_metrics_known_values():
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([12.0, 18.0, 32.0, 38.0])

    res = evaluate_regression(y_true, y_pred)
    metrics = res["metrics"]

    # Absolute errors: 2, 2, 2, 2 -> MAE = 2.0
    assert metrics["mae"] == 2.0
    # Squared errors: 4, 4, 4, 4 -> RMSE = 2.0
    assert metrics["rmse"] == 2.0
    # Total actual = 100, total error = 8 -> WAPE = 0.08
    assert metrics["wape"] == 0.08
    # Variance of y_true = ((10-25)^2 + (20-25)^2 + (30-25)^2 + (40-25)^2) / 4 = 125
    # MSE = 4 -> R^2 = 1 - 4/125 = 0.968
    assert metrics["r2"] == 0.968


def test_regression_inverse_transformation():
    # Original true values in inventory units
    y_true_orig = np.array([100.0, 200.0, 400.0, 800.0])
    y_pred_orig = np.array([110.0, 190.0, 410.0, 790.0])

    # Model was trained in log1p space
    y_true_log = np.log1p(y_true_orig)
    y_pred_log = np.log1p(y_pred_orig)

    # Pass inverse transform np.expm1 so metrics are computed in original inventory units
    res = evaluate_regression(
        y_true=y_true_log,
        y_pred=y_pred_log,
        inverse_transform_fn=np.expm1,
    )
    # In original units, MAE is exactly 10.0
    assert res["metrics"]["mae"] == 10.0
    assert res["metrics"]["rmse"] == 10.0


# ==============================================================================
# 5. BASELINE COMPARISONS
# ==============================================================================

def test_regression_baseline_comparison():
    # Baseline: MAE = 25.0, RMSE = 30.0
    baseline_metrics = {"mae": 25.0, "rmse": 30.0}

    # Candidate 1: MAE = 20.0, RMSE = 28.0 (beats baseline on both)
    y_true = np.array([50.0, 100.0, 150.0])
    y_pred = np.array([70.0, 120.0, 130.0])  # errors: 20, 20, 20 -> MAE=20, RMSE=20

    res = evaluate_regression(
        y_true, y_pred,
        baseline_metrics=baseline_metrics,
        primary_metric="mae",
    )
    comp = res["baseline_comparison"]
    assert comp["beats_baseline"] is True
    assert comp["candidate_value"] == 20.0
    assert comp["baseline_value"] == 25.0

    # Negative R² case where model STILL beats baseline on MAE
    # True values with high outlier variance
    y_true_noisy = np.array([10.0, 10.0, 10.0, 100.0])
    # Baseline dummy predicts constant mean: 32.5 -> errors: 22.5, 22.5, 22.5, 67.5 -> MAE = 33.75
    # Candidate predicts median 10: errors: 0, 0, 0, 90 -> MAE = 22.5 (better MAE than mean baseline!)
    y_cand = np.array([10.0, 10.0, 10.0, 10.0])
    res_sub = evaluate_regression(
        y_true_noisy, y_cand,
        baseline_metrics={"mae": 33.75, "rmse": 45.0},
        primary_metric="mae",
    )
    assert res_sub["baseline_comparison"]["beats_baseline"] is True


def test_classification_baseline_comparison():
    baseline_metrics = {"macro_f1": 0.40, "f1": 0.40}

    # Candidate achieving 0.80 Macro F1
    y_true = np.array(["A", "B", "A", "B"])
    y_pred = np.array(["A", "B", "A", "B"])

    res = evaluate_classification(
        y_true, y_pred,
        baseline_metrics=baseline_metrics,
    )
    comp = res["baseline_comparison"]
    assert comp["beats_baseline"] is True
    assert comp["candidate_value"] == 1.0
    assert comp["baseline_value"] == 0.40


# ==============================================================================
# 6. CONTAMINATION PROPORTIONS AND PERCENTAGE FORMATTING
# ==============================================================================

def test_anomaly_contamination_proportions_and_formatting():
    # 200 validation observations with 4 anomalies flagged
    labels = np.zeros(200, dtype=int)
    labels[:4] = 1  # 4 anomalies
    scores = np.random.RandomState(42).randn(200)

    res = evaluate_anomaly(
        scores=scores,
        labels=labels,
        configured_contamination=0.05,
        y_true=None,  # Unsupervised
    )
    metrics = res["metrics"]

    # Proportion must be strictly in [0, 1]
    assert 0.0 <= metrics["observed_anomaly_rate"] <= 1.0
    assert metrics["observed_anomaly_rate"] == 0.02

    # Percentage representation explicitly converted
    assert metrics["observed_anomaly_pct"] == 2.0
    assert metrics["configured_contamination_rate"] == 0.05
    assert metrics["configured_contamination_pct"] == 5.0
    assert metrics["anomalies_detected"] == 4
    assert metrics["total_observations"] == 200

    # Diagnostic disclaimer for unsupervised detection
    assert any("Ground-truth anomaly labels are unavailable" in w for w in res["warnings"])


def test_anomaly_supervised_evaluation_with_ground_truth():
    labels_pred = np.array([0, 1, 0, 1])
    labels_true = np.array([0, 1, 0, 0])
    scores = np.array([0.1, 0.9, 0.2, 0.8])

    res = evaluate_anomaly(
        scores=scores,
        labels=labels_pred,
        configured_contamination=0.25,
        y_true=labels_true,
    )
    assert res["metrics"]["supervised_accuracy"] == 0.75
    assert "supervised_f1" in res["metrics"]


# ==============================================================================
# 7. TASK-SPECIFIC RANKING AND SAFE MODEL PROMOTION
# ==============================================================================

def test_task_specific_ranking_and_safe_model_promotion(client, owner_user, db):
    headers = owner_user["headers"]

    # 1. Upload dataset
    csv_content = (
        "feature1,feature2,target\n"
        "10,1,100\n"
        "20,2,200\n"
        "30,3,300\n"
        "40,4,400\n"
        "50,5,500\n"
        "60,6,600\n"
        "70,7,700\n"
        "80,8,800\n"
        "90,9,900\n"
        "100,10,1000\n"
    )
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("ranking_test.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Start training with MAE objective
    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "regression", "objective": "mae"},
        headers=headers,
    )
    assert train_res.status_code == 202
    run_id = train_res.json()["id"]

    # Execute training run
    from app.services.ml.orchestrator import run_training_pipeline
    run_training_pipeline(db, run_id)

    # Fetch comparison
    comp_res = client.get(f"/api/v1/training/runs/{run_id}/comparison", headers=headers)
    assert comp_res.status_code == 200
    comp = comp_res.json()

    # Verify primary metric is MAE with lower_is_better direction
    assert comp["primary_metric"] == "mae"
    assert comp["primary_metric_direction"] == "lower_is_better"
    models = comp["metrics_table"]
    assert len(models) > 0

    # Verify ascending sort order by MAE (lowest error first)
    maes = [m["metrics"]["mae"] for m in models if m.get("metrics") and m["metrics"].get("mae") is not None]
    assert maes == sorted(maes)

    # Test safe promotion with baseline check
    best_model = models[0]
    promote_res = client.post(
        f"/api/v1/models/{best_model['id']}/activate?require_beats_baseline=true",
        headers=headers,
    )
    # The best model should activate cleanly
    assert promote_res.status_code == 200
    assert promote_res.json()["is_active"] is True
