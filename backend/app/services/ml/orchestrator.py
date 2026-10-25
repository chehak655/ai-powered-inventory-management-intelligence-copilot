import io
import time
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import joblib

from sklearn.dummy import DummyRegressor, DummyClassifier
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, accuracy_score, f1_score
import xgboost as xgb

from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetConfiguration
from app.models.training import TrainingRun, CandidateModel
from app.services.storage import storage_service
from app.services.dataset_service import parse_dataset_bytes
from app.services.ml.preprocessing import (
    RobustFeaturePreprocessor,
    analyze_target_cardinality,
    split_data,
)
from app.services.ml.forecasting import (
    NaiveForecaster,
    SeasonalNaiveForecaster,
    engineer_forecasting_features,
)
from app.services.ml.evaluator import (
    evaluate_regression,
    evaluate_classification,
    evaluate_anomaly,
)


def run_training_pipeline(db: Session, training_run_id: str) -> None:
    """
    Execute end-to-end model training run in controlled background execution.
    Fails safely per-model so single algorithm errors do not abort the entire run.
    Integrates robust preprocessing, leak-free validation, and baseline benchmarking.
    """
    run = db.query(TrainingRun).filter(TrainingRun.id == training_run_id).first()
    if not run:
        return

    run.status = "RUNNING"
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    start_time = time.time()

    try:
        # Load authorized dataset from storage
        dataset = db.query(Dataset).filter(Dataset.id == run.dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {run.dataset_id} not found in database.")

        raw_bytes = storage_service.read_file(run.company_id, dataset.storage_identifier)
        df = parse_dataset_bytes(raw_bytes, dataset.original_filename)

        task_type = run.task_type
        target_col = run.target_column
        feature_cols = run.feature_columns or []
        date_col = run.date_column
        entity_cols = run.entity_columns or []

        # Validate task columns exist in df
        for f in feature_cols:
            if f not in df.columns:
                raise ValueError(f"Feature column '{f}' missing from dataset.")

        val_time_range = None
        classes = None
        class_to_idx = None
        inference_feature_cols = feature_cols
        target_stats = {}

        # -------------------------------------------------------------
        # TASK 1: TIME-SERIES DEMAND FORECASTING
        # -------------------------------------------------------------
        if task_type == "forecasting":
            if not date_col or date_col not in df.columns:
                raise ValueError(f"Date column '{date_col}' required for time-series forecasting.")
            if not target_col or target_col not in df.columns:
                raise ValueError(f"Target column '{target_col}' required for time-series forecasting.")

            # Construct group-aware lags & calendar features
            feat_df, generated_feature_cols, _ = engineer_forecasting_features(
                df=df,
                date_col=date_col,
                target_col=target_col,
                entity_cols=entity_cols,
                feature_cols=feature_cols,
            )

            # Target statistics
            target_stats = analyze_target_cardinality(feat_df[target_col], task_type)

            # Chronological partitioning
            train_df, val_df, y_train_s, y_val_s = split_data(
                df=feat_df,
                target_col=target_col,
                task_type="forecasting",
                val_size=0.25,
                date_col=date_col,
            )

            y_train = np.asarray(y_train_s, dtype=float)
            y_val = np.asarray(y_val_s, dtype=float)

            run.train_row_count = len(train_df)
            run.val_row_count = len(val_df)
            val_dates = pd.to_datetime(val_df[date_col]).dropna()
            if len(val_dates) > 0:
                val_time_range = {
                    "start": str(val_dates.min()),
                    "end": str(val_dates.max()),
                }
            run.val_time_range = val_time_range

            # Adaptive preprocessor fitted strictly on training partition
            preprocessor = RobustFeaturePreprocessor(top_k_categories=15)
            X_train = preprocessor.fit_transform(train_df, generated_feature_cols)
            X_val = preprocessor.transform(val_df)
            proc_feature_names = preprocessor.feature_names_out_
            inference_feature_cols = generated_feature_cols

            candidates = [
                ("naive_forecasting", "Naive Baseline (Last Value)", "baseline", NaiveForecaster(), {}),
                ("seasonal_naive_forecasting", "Seasonal Naive (7-Period)", "baseline", SeasonalNaiveForecaster(7), {"season_length": 7}),
                ("supervised_lag_rf", "Lag-Enhanced Random Forest", "tree", RandomForestRegressor(n_estimators=100, max_depth=6, min_samples_leaf=2, random_state=42), {"n_estimators": 100, "max_depth": 6}),
                ("supervised_lag_xgb", "Lag-Enhanced XGBoost", "ensemble", xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, subsample=0.8, reg_alpha=0.1, random_state=42, verbosity=0), {"n_estimators": 100, "max_depth": 4}),
            ]

        # -------------------------------------------------------------
        # TASK 2: NUMERIC REGRESSION
        # -------------------------------------------------------------
        elif task_type == "regression":
            if not target_col or target_col not in df.columns:
                raise ValueError(f"Target column '{target_col}' required for regression.")

            # Filter valid target rows
            clean_df = df.dropna(subset=[target_col]).copy()
            clean_df[target_col] = pd.to_numeric(clean_df[target_col], errors="coerce")
            clean_df = clean_df.dropna(subset=[target_col])

            target_stats = analyze_target_cardinality(clean_df[target_col], task_type)

            # Prevent feature leakage: drop target if accidentally present in feature_cols
            valid_feature_cols = [f for f in feature_cols if f != target_col and f in clean_df.columns]
            if not valid_feature_cols:
                raise ValueError("No valid predictor features available for regression.")

            X_train_df, X_val_df, y_train_s, y_val_s = split_data(
                clean_df,
                target_col=target_col,
                task_type="regression",
                val_size=0.2,
            )

            run.train_row_count = len(X_train_df)
            run.val_row_count = len(X_val_df)
            y_train = np.asarray(y_train_s, dtype=float)
            y_val = np.asarray(y_val_s, dtype=float)

            # Adaptive preprocessor fitted strictly on training partition
            preprocessor = RobustFeaturePreprocessor(top_k_categories=15)
            X_train = preprocessor.fit_transform(X_train_df, valid_feature_cols)
            X_val = preprocessor.transform(X_val_df)
            proc_feature_names = preprocessor.feature_names_out_
            inference_feature_cols = valid_feature_cols

            candidates = [
                ("median_baseline", "Median Baseline", "baseline", DummyRegressor(strategy="median"), {}),
                ("linear_regression", "Linear Regression (Ridge L2)", "linear", Ridge(alpha=1.0, random_state=42), {"alpha": 1.0}),
                ("random_forest_regressor", "Random Forest Regressor", "tree", RandomForestRegressor(n_estimators=100, max_depth=8, min_samples_leaf=3, max_features="sqrt", random_state=42), {"n_estimators": 100, "max_depth": 8}),
                ("xgboost_regressor", "XGBoost Regressor", "ensemble", xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, subsample=0.8, reg_alpha=0.2, reg_lambda=1.0, random_state=42, verbosity=0), {"n_estimators": 100, "max_depth": 4}),
            ]

        # -------------------------------------------------------------
        # TASK 3: CLASSIFICATION
        # -------------------------------------------------------------
        elif task_type == "classification":
            if not target_col or target_col not in df.columns:
                raise ValueError(f"Target column '{target_col}' required for classification.")

            clean_df = df.dropna(subset=[target_col]).copy()
            clean_df[target_col] = clean_df[target_col].astype(str).str.strip()

            target_stats = analyze_target_cardinality(clean_df[target_col], task_type)

            valid_feature_cols = [f for f in feature_cols if f != target_col and f in clean_df.columns]
            if not valid_feature_cols:
                raise ValueError("No valid predictor features available for classification.")

            X_train_df, X_val_df, y_train_s, y_val_s = split_data(
                clean_df,
                target_col=target_col,
                task_type="classification",
                val_size=0.2,
            )

            run.train_row_count = len(X_train_df)
            run.val_row_count = len(X_val_df)
            y_train = np.asarray(y_train_s)
            y_val = np.asarray(y_val_s)

            preprocessor = RobustFeaturePreprocessor(top_k_categories=15)
            X_train = preprocessor.fit_transform(X_train_df, valid_feature_cols)
            X_val = preprocessor.transform(X_val_df)
            proc_feature_names = preprocessor.feature_names_out_
            inference_feature_cols = valid_feature_cols

            classes = np.unique(y_train)
            class_to_idx = {c: i for i, c in enumerate(classes)}
            y_train_idx = np.array([class_to_idx.get(val, 0) for val in y_train])

            candidates = [
                ("dummy_classifier", "Most Frequent Baseline", "baseline", DummyClassifier(strategy="most_frequent"), {}),
                ("logistic_regression", "Logistic Regression (Balanced)", "linear", LogisticRegression(class_weight="balanced", C=1.0, max_iter=500, random_state=42), {"class_weight": "balanced", "max_iter": 500}),
                ("random_forest_classifier", "Random Forest Classifier (Balanced)", "tree", RandomForestClassifier(n_estimators=100, max_depth=8, min_samples_leaf=2, class_weight="balanced", random_state=42), {"n_estimators": 100, "max_depth": 8, "class_weight": "balanced"}),
                ("xgboost_classifier", "XGBoost Classifier", "ensemble", xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, subsample=0.8, reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbosity=0), {"n_estimators": 100, "max_depth": 4}),
            ]

        # -------------------------------------------------------------
        # TASK 4: ANOMALY DETECTION
        # -------------------------------------------------------------
        elif task_type == "anomaly":
            clean_df = df.copy()
            valid_feature_cols = [f for f in feature_cols if f in clean_df.columns]

            X_train_df, X_val_df, _, _ = split_data(
                clean_df,
                target_col=None,
                task_type="anomaly",
                val_size=0.2,
            )

            run.train_row_count = len(X_train_df)
            run.val_row_count = len(X_val_df)

            preprocessor = RobustFeaturePreprocessor(top_k_categories=15)
            X_train = preprocessor.fit_transform(X_train_df, valid_feature_cols)
            X_val = preprocessor.transform(X_val_df)
            proc_feature_names = preprocessor.feature_names_out_
            inference_feature_cols = valid_feature_cols

            candidates = [
                ("isolation_forest", "Isolation Forest", "anomaly", IsolationForest(contamination=0.05, random_state=42), {"contamination": 0.05}),
            ]
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

        # Update run configuration preserving objective and columns while adding diagnostic stats
        current_config = dict(run.configuration or {})
        current_config.update({
            "target_diagnostics": target_stats,
            "processed_feature_count": len(proc_feature_names),
        })
        run.configuration = current_config
        db.commit()

        # Benchmark baseline first to enable comparative scoring
        successful_count = 0
        failed_count = 0
        baseline_metrics_dict: Dict[str, Any] = {}

        for algo_key, display_name, family, estimator, params in candidates:
            m_start = time.time()
            cand_record = CandidateModel(
                company_id=run.company_id,
                training_run_id=run.id,
                dataset_id=run.dataset_id,
                algorithm=algo_key,
                algorithm_display_name=display_name,
                model_family=family,
                hyperparameters=params,
                status="SUCCESS",
            )
            db.add(cand_record)
            db.flush()

            try:
                train_metrics: Dict[str, Any] = {}

                # Fit estimator
                if task_type in ["regression", "forecasting"]:
                    estimator.fit(X_train, y_train)
                    y_pred = estimator.predict(X_val)
                    y_train_pred = estimator.predict(X_train)
                    configured_objective = (run.configuration or {}).get("objective", "rmse")
                    eval_res = evaluate_regression(
                        y_true=y_val,
                        y_pred=y_pred,
                        feature_names=proc_feature_names,
                        estimator=estimator,
                        baseline_metrics=baseline_metrics_dict if family != "baseline" else None,
                        primary_metric=configured_objective,
                    )
                    train_rmse = float(np.sqrt(mean_squared_error(y_train, y_train_pred)))
                    train_mae = float(mean_absolute_error(y_train, y_train_pred))
                    train_r2 = float(r2_score(y_train, y_train_pred)) if np.var(y_train) > 1e-8 else 0.0
                    train_metrics = {
                        "rmse": round(train_rmse, 4),
                        "mae": round(train_mae, 4),
                        "r2": round(train_r2, 4),
                    }
                    if family == "baseline" and ("rmse" in eval_res["metrics"] or "mae" in eval_res["metrics"]):
                        baseline_metrics_dict = eval_res["metrics"]

                elif task_type == "classification":
                    if algo_key == "xgboost_classifier":
                        estimator.fit(X_train, y_train_idx)
                        pred_indices = estimator.predict(X_val)
                        idx_to_class = {i: c for c, i in class_to_idx.items()}
                        y_pred = np.array([idx_to_class.get(idx, classes[0]) for idx in pred_indices])
                        y_prob = estimator.predict_proba(X_val) if hasattr(estimator, "predict_proba") else None
                        train_indices = estimator.predict(X_train)
                        y_train_pred = np.array([idx_to_class.get(idx, classes[0]) for idx in train_indices])
                    else:
                        estimator.fit(X_train, y_train)
                        y_pred = estimator.predict(X_val)
                        y_prob = estimator.predict_proba(X_val) if hasattr(estimator, "predict_proba") else None
                        y_train_pred = estimator.predict(X_train)

                    eval_res = evaluate_classification(
                        y_true=y_val,
                        y_pred=y_pred,
                        y_prob=y_prob,
                        feature_names=proc_feature_names,
                        estimator=estimator,
                        baseline_metrics=baseline_metrics_dict if family != "baseline" else None,
                        classes=classes,
                    )
                    train_acc = float(accuracy_score(y_train, y_train_pred))
                    train_f1 = float(f1_score(y_train, y_train_pred, average="macro", zero_division=0))
                    train_metrics = {
                        "accuracy": round(train_acc, 4),
                        "macro_f1": round(train_f1, 4),
                    }
                    if family == "baseline" and ("macro_f1" in eval_res["metrics"] or "f1" in eval_res["metrics"]):
                        baseline_metrics_dict = eval_res["metrics"]

                elif task_type == "anomaly":
                    estimator.fit(X_train)
                    scores = -estimator.decision_function(X_val)
                    raw_labels = estimator.predict(X_val)
                    labels = np.where(raw_labels == -1, 1, 0)
                    configured_contam = params.get("contamination", 0.05)
                    eval_res = evaluate_anomaly(
                        scores=scores,
                        labels=labels,
                        configured_contamination=configured_contam,
                    )
                    train_metrics = {
                        "configured_contamination": configured_contam,
                    }

                m_duration = round(time.time() - m_start, 3)

                # Generate evidence-based performance diagnosis
                perf_explanation = None
                overfitting_risk = False
                base_comp = eval_res.get("baseline_comparison", {})
                beats_baseline = base_comp.get("beats_baseline", True) if family != "baseline" else True

                if task_type in ["regression", "forecasting"]:
                    val_r2 = eval_res["metrics"].get("r2")
                    train_r2 = train_metrics.get("r2", 0.0)
                    if train_r2 > 0.6 and (val_r2 is not None and val_r2 < 0.1):
                        overfitting_risk = True
                        perf_explanation = (
                            f"Model is overfitting the training partition (Train R² = {train_r2:.2f} vs Validation R² = {val_r2:.2f}). "
                            f"Generalization error on unseen validation holdout is significantly larger than training loss."
                        )
                    elif val_r2 is not None and val_r2 <= 0.0:
                        perf_explanation = (
                            f"Model R² ({val_r2:.4f}) does not explain significant target variance compared to the horizontal baseline. "
                            f"Predictor features exhibit weak linear/tree correlation with target variable '{target_col}'."
                        )
                elif task_type == "classification":
                    val_macro_f1 = eval_res["metrics"].get("macro_f1", 0.0)
                    train_f1 = train_metrics.get("macro_f1", 0.0)
                    n_classes = len(classes) if classes is not None else 0
                    if n_classes > 15:
                        perf_explanation = (
                            f"Performance is constrained by high class cardinality ({n_classes} classes) with extreme data sparsity "
                            f"in validation holdout. Treating continuous numeric quantities as unbinned discrete classes inherently degrades Macro-F1."
                        )
                    elif not beats_baseline:
                        perf_explanation = (
                            f"Candidate model (Macro-F1 {val_macro_f1:.4f}) does not outperform the majority baseline "
                            f"(Macro-F1 {base_comp.get('baseline_value', 0):.4f}). Class imbalance limits minority-class generalization."
                        )

                # Add diagnostic warnings if any
                combined_warnings = list(eval_res.get("warnings", []))
                if target_stats.get("warning"):
                    combined_warnings.append(target_stats["warning"])
                if perf_explanation:
                    combined_warnings.append(perf_explanation)

                # Build summary object for registry & comparisons
                eval_summary = {
                    "metric_definitions": eval_res.get("metric_definitions", {}),
                    "baseline_comparison": eval_res.get("baseline_comparison", {}),
                    "residual_analysis": eval_res.get("residual_analysis", {}),
                    "confusion_matrix": eval_res.get("confusion_matrix"),
                    "per_class_summary": eval_res.get("per_class_summary", {}),
                    "score_quantiles": eval_res.get("score_quantiles", {}),
                    "warnings": combined_warnings,
                    "target_summary": target_stats.get("summary") or target_stats.get("class_distribution", {}),
                    "train_metrics": train_metrics,
                    "overfitting_risk": overfitting_risk,
                    "performance_explanation": perf_explanation,
                }

                # Serialize artifact bundle via Joblib
                artifact_bundle = {
                    "task_type": task_type,
                    "algorithm": algo_key,
                    "target_column": target_col,
                    "feature_columns": feature_cols,
                    "inference_feature_columns": inference_feature_cols,
                    "date_column": date_col,
                    "entity_columns": entity_cols,
                    "preprocessor": preprocessor,
                    "estimator": estimator,
                    "feature_names": proc_feature_names,
                    "classes": classes.tolist() if isinstance(classes, np.ndarray) else classes,
                    "class_to_idx": class_to_idx,
                    "metrics": eval_res["metrics"],
                    "evaluation_summary": eval_summary,
                    "baseline_metrics": baseline_metrics_dict,
                    "train_metrics": train_metrics,
                    "performance_explanation": perf_explanation,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                buf = io.BytesIO()
                joblib.dump(artifact_bundle, buf, compress=3)
                artifact_bytes = buf.getvalue()

                storage_id = storage_service.save_file(
                    company_id=run.company_id,
                    content=artifact_bytes,
                    extension=".joblib",
                    subfolder="models",
                )

                cand_record.metrics = eval_res["metrics"]
                cand_record.evaluation_summary = eval_summary
                cand_record.sample_predictions = eval_res["sample_predictions"]
                cand_record.feature_importances = eval_res.get("feature_importances", {})
                cand_record.storage_identifier = storage_id
                cand_record.artifact_size_bytes = len(artifact_bytes)
                cand_record.training_duration_seconds = m_duration
                cand_record.status = "SUCCESS"
                successful_count += 1

            except Exception as model_err:
                m_duration = round(time.time() - m_start, 3)
                cand_record.status = "FAILED"
                cand_record.error_details = str(model_err)[:900]
                cand_record.training_duration_seconds = m_duration
                failed_count += 1

            db.commit()

        total_duration = round(time.time() - start_time, 2)
        run.duration_seconds = total_duration
        run.completed_at = datetime.now(timezone.utc)
        run.candidate_count = len(candidates)

        if successful_count > 0 and failed_count == 0:
            run.status = "COMPLETED"
        elif successful_count > 0 and failed_count > 0:
            run.status = "PARTIALLY_FAILED"
        else:
            run.status = "FAILED"
            run.error_message = "All candidate models failed during training."

        db.commit()

    except Exception as run_err:
        total_duration = round(time.time() - start_time, 2)
        run.duration_seconds = total_duration
        run.completed_at = datetime.now(timezone.utc)
        run.status = "FAILED"
        run.error_message = str(run_err)[:950]
        db.commit()
