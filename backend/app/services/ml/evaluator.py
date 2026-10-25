import math
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)


def safe_float(val: Any) -> Optional[float]:
    """Convert float safely for JSON, replacing NaN/Inf with None."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None


def evaluate_regression(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    feature_names: Optional[List[str]] = None,
    estimator: Any = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
    primary_metric: str = "rmse",
    inverse_transform_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Compute regression and forecasting evaluation metrics:
    MAE, RMSE, WAPE, R-squared, residuals analysis, and baseline comparison.
    Applies optional inverse_transform_fn so all metrics and residuals are in original target units.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    valid_mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    y_true = y_true[valid_mask]
    y_pred = y_pred[valid_mask]

    # Invert any target scaling/log transform to compute metrics in true physical/business units
    if inverse_transform_fn is not None:
        try:
            y_true = np.asarray(inverse_transform_fn(y_true), dtype=float)
            y_pred = np.asarray(inverse_transform_fn(y_pred), dtype=float)
        except Exception:
            pass

    n_samples = len(y_true)
    if n_samples == 0:
        return {
            "metrics": {"mae": None, "rmse": None, "wape": None, "r2": None},
            "metric_definitions": {},
            "sample_predictions": [],
            "feature_importances": {},
            "residual_analysis": {},
            "warnings": ["Evaluation dataset contained zero valid target records."],
        }

    # Error metrics
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    sum_y = np.sum(np.abs(y_true))
    wape = np.sum(np.abs(y_true - y_pred)) / sum_y if sum_y > 1e-8 else None

    # R2 variance check
    var_y = np.var(y_true)
    if var_y > 1e-8:
        try:
            r2 = r2_score(y_true, y_pred)
        except Exception:
            r2 = None
    else:
        r2 = 0.0

    residuals = y_true - y_pred
    mean_res = float(np.mean(residuals))
    std_res = float(np.std(residuals))
    max_err = float(np.max(np.abs(residuals)))

    metrics = {
        "mae": safe_float(mae),
        "rmse": safe_float(rmse),
        "wape": safe_float(wape),
        "r2": safe_float(r2),
    }

    warnings: List[str] = []
    if r2 is not None and r2 < 0.0:
        warnings.append(
            f"Model R² is negative ({r2:.4f}). Predictions have higher error variance than the mean baseline. "
            f"This often indicates uninformative features or lack of linear/tree correlation with the target."
        )

    # Baseline comparison on configured objective (e.g. MAE or RMSE)
    baseline_comp = {}
    if baseline_metrics:
        # Check primary metric (defaulting to rmse, or mae if requested)
        obj_key = primary_metric.lower() if primary_metric.lower() in ["mae", "rmse", "wape"] else "rmse"
        base_val = baseline_metrics.get(obj_key)
        cand_val = metrics.get(obj_key)
        base_mae = baseline_metrics.get("mae")

        beats_primary = bool(cand_val < base_val) if (cand_val is not None and base_val is not None) else False
        beats_mae = bool(mae < base_mae) if (base_mae is not None) else beats_primary

        abs_imp = safe_float(base_val - cand_val) if (base_val is not None and cand_val is not None) else None
        imp_pct = safe_float(((base_val - cand_val) / max(base_val, 1e-6)) * 100) if (base_val is not None and cand_val is not None) else None

        baseline_comp = {
            "primary_metric": obj_key,
            "baseline_value": safe_float(base_val),
            "candidate_value": safe_float(cand_val),
            "baseline_mae": safe_float(base_mae),
            "candidate_mae": safe_float(mae),
            "beats_baseline": beats_primary,
            "beats_mae": beats_mae,
            "absolute_improvement": abs_imp,
            "improvement_pct": imp_pct,
        }

    metric_definitions = {
        "rmse": {"name": "Root Mean Squared Error", "higher_is_better": False, "description": "Penalizes larger outliers more heavily in original target units."},
        "mae": {"name": "Mean Absolute Error", "higher_is_better": False, "description": "Average magnitude of absolute prediction errors in original target units."},
        "wape": {"name": "Weighted Absolute Percentage Error", "higher_is_better": False, "description": "Total absolute error divided by total demand."},
        "r2": {"name": "R-Squared", "higher_is_better": True, "description": "Variance explained relative to horizontal mean (max 1.0; negative indicates worse than mean)."},
    }

    # Sample predictions for visualization charts (up to 40 evenly-spaced points)
    sample_preds = []
    step = max(1, n_samples // 40)
    for i in range(0, n_samples, step):
        act = float(y_true[i])
        prd = float(y_pred[i])
        sample_preds.append({
            "index": i,
            "actual": safe_float(act),
            "predicted": safe_float(prd),
            "residual": safe_float(act - prd),
        })

    # Feature importance extraction
    feature_importances = {}
    if estimator is not None and feature_names:
        try:
            if hasattr(estimator, "feature_importances_"):
                fi = estimator.feature_importances_
                for f_name, imp in zip(feature_names, fi):
                    feature_importances[f_name] = safe_float(imp)
            elif hasattr(estimator, "coef_"):
                coef = np.abs(estimator.coef_)
                if coef.ndim > 1:
                    coef = coef[0]
                total = np.sum(coef) if np.sum(coef) > 0 else 1.0
                norm_coef = coef / total
                for f_name, imp in zip(feature_names, norm_coef):
                    feature_importances[f_name] = safe_float(imp)
        except Exception:
            pass

    return {
        "metrics": metrics,
        "metric_definitions": metric_definitions,
        "sample_predictions": sample_preds,
        "feature_importances": feature_importances,
        "residual_analysis": {
            "mean_residual": safe_float(mean_res),
            "std_residual": safe_float(std_res),
            "max_error": safe_float(max_err),
        },
        "baseline_comparison": baseline_comp,
        "warnings": warnings,
    }


def evaluate_classification(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
    feature_names: Optional[List[str]] = None,
    estimator: Any = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
    classes: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Compute multi-class and binary classification metrics:
    Accuracy, Macro-F1, Weighted-F1, Precision, Recall, Confusion Matrix, and ROC-AUC.
    Computes ROC-AUC robustly by mapping class probabilities to known validation labels.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    n_samples = len(y_true)

    if n_samples == 0:
        return {
            "metrics": {
                "macro_f1": None,
                "weighted_f1": None,
                "accuracy": None,
                "precision": None,
                "recall": None,
                "roc_auc": None,
                "f1": None,
            },
            "metric_definitions": {},
            "sample_predictions": [],
            "feature_importances": {},
            "confusion_matrix": None,
            "warnings": ["Evaluation dataset contained zero valid classification records."],
        }

    unique_classes = np.unique(np.concatenate([y_true, y_pred]))
    n_classes = len(unique_classes)

    acc = accuracy_score(y_true, y_pred)
    # Macro F1 treats each class equally (critical for class imbalance)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
    macro_prec = precision_score(y_true, y_pred, average="macro", zero_division=0)
    macro_rec = recall_score(y_true, y_pred, average="macro", zero_division=0)

    # Determine class order matching probability matrix columns
    if classes is not None:
        model_classes = list(classes)
    elif estimator is not None and hasattr(estimator, "classes_"):
        model_classes = list(estimator.classes_)
    else:
        model_classes = list(unique_classes)

    # ROC-AUC calculation with robust label alignment
    roc_auc = None
    if y_prob is not None:
        try:
            prob_arr = np.asarray(y_prob)
            if len(model_classes) == 2:
                # Binary classification: positive class is model_classes[1]
                pos_label = model_classes[1]
                binary_y = (y_true == pos_label).astype(int)
                # Both classes must be present in validation partition to define ROC-AUC
                if len(np.unique(binary_y)) == 2:
                    if prob_arr.ndim == 2 and prob_arr.shape[1] >= 2:
                        pos_scores = prob_arr[:, 1]
                    else:
                        pos_scores = prob_arr.ravel()
                    roc_auc = roc_auc_score(binary_y, pos_scores)
            elif len(model_classes) > 2 and prob_arr.ndim == 2:
                # Multi-class OvR Macro ROC-AUC: compute per-class AUC over classes present in validation partition
                per_class_aucs = []
                for idx, cls_val in enumerate(model_classes):
                    if idx >= prob_arr.shape[1]:
                        continue
                    bin_y = (y_true == cls_val).astype(int)
                    # Class must have at least 1 positive and 1 negative example in validation partition
                    if len(np.unique(bin_y)) == 2:
                        try:
                            score_c = roc_auc_score(bin_y, prob_arr[:, idx])
                            per_class_aucs.append(score_c)
                        except Exception:
                            pass
                if len(per_class_aucs) > 0:
                    roc_auc = float(np.mean(per_class_aucs))
        except Exception:
            roc_auc = None

    metrics = {
        "macro_f1": safe_float(macro_f1),
        "weighted_f1": safe_float(weighted_f1),
        "accuracy": safe_float(acc),
        "precision": safe_float(macro_prec),
        "recall": safe_float(macro_rec),
        "roc_auc": safe_float(roc_auc),
        "f1": safe_float(macro_f1),  # Backward compatibility alias
    }

    warnings: List[str] = []
    if n_classes > 20:
        warnings.append(
            f"Target has {n_classes} classes. High-cardinality multi-class classification typically yields low F1 scores. "
            f"Consider grouping sparse categories or formulating as numeric regression if ordinal/continuous."
        )

    # Confusion matrix
    conf_mat = None
    per_class_summary = {}
    try:
        cm = confusion_matrix(y_true, y_pred, labels=unique_classes)
        conf_mat = {
            "classes": [str(c) for c in unique_classes],
            "matrix": cm.tolist(),
        }
        # Per class stats
        for idx, cls_name in enumerate(unique_classes):
            cls_mask_true = (y_true == cls_name)
            cls_mask_pred = (y_pred == cls_name)
            support = int(np.sum(cls_mask_true))
            tp = int(np.sum(cls_mask_true & cls_mask_pred))
            fp = int(np.sum(~cls_mask_true & cls_mask_pred))
            fn = int(np.sum(cls_mask_true & ~cls_mask_pred))
            p = tp / max(tp + fp, 1)
            r = tp / max(tp + fn, 1)
            f = (2 * p * r) / max(p + r, 1e-6)
            per_class_summary[str(cls_name)] = {
                "support": support,
                "precision": safe_float(p),
                "recall": safe_float(r),
                "f1": safe_float(f),
            }
    except Exception:
        conf_mat = None

    # Baseline comparison (benchmarks Macro-F1)
    baseline_comp = {}
    if baseline_metrics:
        base_f1 = baseline_metrics.get("macro_f1") or baseline_metrics.get("f1")
        if base_f1 is not None:
            beats_f1 = bool(macro_f1 > base_f1)
            abs_imp = safe_float(macro_f1 - base_f1)
            imp_pct = safe_float(((macro_f1 - base_f1) / max(base_f1, 1e-6)) * 100) if base_f1 > 1e-6 else None
            baseline_comp = {
                "primary_metric": "macro_f1",
                "baseline_value": safe_float(base_f1),
                "candidate_value": safe_float(macro_f1),
                "baseline_f1": safe_float(base_f1),
                "candidate_f1": safe_float(macro_f1),
                "beats_baseline": beats_f1,
                "absolute_improvement": abs_imp,
                "improvement": abs_imp,  # Backward compatibility
                "improvement_pct": imp_pct,
            }

    metric_definitions = {
        "macro_f1": {"name": "Macro F1-Score", "higher_is_better": True, "description": "Unweighted mean of F1 scores across all classes. Evaluates performance equally regardless of class imbalance."},
        "weighted_f1": {"name": "Weighted F1-Score", "higher_is_better": True, "description": "F1 score weighted by class prevalence in the validation set."},
        "accuracy": {"name": "Accuracy", "higher_is_better": True, "description": "Proportion of total correct predictions across evaluated validation examples."},
        "precision": {"name": "Macro Precision", "higher_is_better": True, "description": "Unweighted average precision across all classes."},
        "recall": {"name": "Macro Recall", "higher_is_better": True, "description": "Unweighted average recall across all classes."},
        "roc_auc": {"name": "ROC-AUC", "higher_is_better": True, "description": "Area under the Receiver Operating Characteristic curve across evaluatable classes."},
        "f1": {"name": "Macro F1-Score", "higher_is_better": True, "description": "Standard Macro F1-Score (unweighted)."},
    }

    sample_preds = []
    step = max(1, n_samples // 40)
    for i in range(0, n_samples, step):
        sample_preds.append({
            "index": i,
            "actual": str(y_true[i]),
            "predicted": str(y_pred[i]),
            "correct": bool(y_true[i] == y_pred[i]),
        })

    feature_importances = {}
    if estimator is not None and feature_names:
        try:
            if hasattr(estimator, "feature_importances_"):
                fi = estimator.feature_importances_
                for f_name, imp in zip(feature_names, fi):
                    feature_importances[f_name] = safe_float(imp)
            elif hasattr(estimator, "coef_"):
                coef = np.abs(estimator.coef_)
                if coef.ndim > 1:
                    coef = np.mean(coef, axis=0)
                total = np.sum(coef) if np.sum(coef) > 0 else 1.0
                norm_coef = coef / total
                for f_name, imp in zip(feature_names, norm_coef):
                    feature_importances[f_name] = safe_float(imp)
        except Exception:
            pass

    return {
        "metrics": metrics,
        "metric_definitions": metric_definitions,
        "sample_predictions": sample_preds,
        "feature_importances": feature_importances,
        "confusion_matrix": conf_mat,
        "per_class_summary": per_class_summary,
        "baseline_comparison": baseline_comp,
        "warnings": warnings,
    }


def evaluate_anomaly(
    scores: np.ndarray,
    labels: np.ndarray,
    configured_contamination: Optional[float] = None,
    y_true: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Compute anomaly detection output diagnostics:
    Observed anomaly rate [0, 1], percentage formatting, score distribution quantiles,
    and clear distinction between configured parameter and observed diagnostics.
    Labels: 1 = Anomaly, 0 = Normal.
    """
    n_samples = len(labels)
    anomaly_count = int(np.sum(labels == 1))
    
    # Observed fraction of validation examples predicted as anomalies (strictly validated in [0, 1])
    observed_rate = float(anomaly_count / max(n_samples, 1))
    observed_rate = max(0.0, min(1.0, observed_rate))
    observed_pct = round(observed_rate * 100, 2)

    # Configured contamination parameter (strictly validated in [0, 1])
    conf_rate = None
    conf_pct = None
    if configured_contamination is not None:
        try:
            c = float(configured_contamination)
            conf_rate = max(0.0, min(1.0, c))
            conf_pct = round(conf_rate * 100, 2)
        except (ValueError, TypeError):
            pass

    score_quantiles = {}
    if n_samples > 0:
        score_quantiles = {
            "p25": safe_float(np.percentile(scores, 25)),
            "p50": safe_float(np.percentile(scores, 50)),
            "p75": safe_float(np.percentile(scores, 75)),
            "p90": safe_float(np.percentile(scores, 90)),
            "p95": safe_float(np.percentile(scores, 95)),
        }

    metrics = {
        "observed_anomaly_rate": safe_float(observed_rate),  # Proportion in [0, 1]
        "observed_anomaly_pct": safe_float(observed_pct),    # Percentage (e.g. 2.02%)
        "configured_contamination_rate": safe_float(conf_rate),  # Proportion in [0, 1]
        "configured_contamination_pct": safe_float(conf_pct),    # Percentage (e.g. 5.0%)
        "contamination_rate": safe_float(observed_rate),     # Proportion in [0, 1] for backward compat
        "anomalies_detected": anomaly_count,
        "total_observations": n_samples,
        "min_score": safe_float(np.min(scores)) if n_samples > 0 else None,
        "mean_score": safe_float(np.mean(scores)) if n_samples > 0 else None,
        "max_score": safe_float(np.max(scores)) if n_samples > 0 else None,
    }

    warnings: List[str] = []
    # If ground-truth anomaly labels are unavailable, explain that supervised quality cannot be inferred
    if y_true is None:
        warnings.append(
            "Ground-truth anomaly labels are unavailable (unsupervised detection). "
            "Contamination rate and flagged anomaly count are diagnostic indicators of decision boundary density, "
            "not supervised detection accuracy or quality."
        )
    else:
        # Supervised metrics when labels are present
        try:
            sup_acc = accuracy_score(y_true, labels)
            sup_f1 = f1_score(y_true, labels, zero_division=0)
            metrics["supervised_accuracy"] = safe_float(sup_acc)
            metrics["supervised_f1"] = safe_float(sup_f1)
        except Exception:
            pass

    metric_definitions = {
        "observed_anomaly_rate": {"name": "Observed Anomaly Rate", "higher_is_better": None, "description": "Proportion of validation examples flagged as anomalous [0.0 to 1.0]."},
        "observed_anomaly_pct": {"name": "Observed Anomaly %", "higher_is_better": None, "description": "Percentage of validation observations flagged as outliers."},
        "configured_contamination_rate": {"name": "Configured Contamination", "higher_is_better": None, "description": "Configured model parameter representing prior expected outlier proportion."},
        "anomalies_detected": {"name": "Flagged Anomalies", "higher_is_better": None, "description": "Number of flagged irregular records in validation partition."},
        "contamination_rate": {"name": "Observed Anomaly Rate", "higher_is_better": None, "description": "Proportion of validation observations flagged as anomalous [0.0 to 1.0]."},
    }

    sample_preds = []
    step = max(1, n_samples // 50)
    for i in range(0, n_samples, step):
        sample_preds.append({
            "index": i,
            "score": safe_float(scores[i]),
            "is_anomaly": bool(labels[i] == 1),
        })

    return {
        "metrics": metrics,
        "metric_definitions": metric_definitions,
        "sample_predictions": sample_preds,
        "feature_importances": {},
        "score_quantiles": score_quantiles,
        "warnings": warnings,
    }
