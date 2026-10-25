import io
import time
from typing import Dict, Any, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.training import CandidateModel
from app.models.prediction import PredictionLog
from app.services.storage import storage_service


class PredictionService:
    @staticmethod
    def load_model_artifact(company_id: str, storage_identifier: str) -> Dict[str, Any]:
        """Load and deserialize model artifact bundle from storage."""
        try:
            artifact_bytes = storage_service.load_file(company_id, storage_identifier)
            return joblib.load(io.BytesIO(artifact_bytes))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to load model artifact: {str(e)}",
            )

    @classmethod
    def execute_prediction(
        cls,
        db: Session,
        company_id: str,
        model_id: str,
        input_df: pd.DataFrame,
        prediction_type: str = "single",
    ) -> Dict[str, Any]:
        """
        Execute prediction pipeline for single or batch inputs on an authorized candidate model.
        Returns prediction outputs, probabilities, latency, and logs the execution.
        """
        start_time = time.time()

        # 1. Authorize model within active tenant
        model = (
            db.query(CandidateModel)
            .filter(
                CandidateModel.id == model_id,
                CandidateModel.company_id == company_id,
            )
            .first()
        )
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found in this company workspace.",
            )

        if model.status != "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model status is {model.status}; cannot generate predictions.",
            )

        if not model.storage_identifier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model artifact missing from storage.",
            )

        # 2. Load artifact bundle
        bundle = cls.load_model_artifact(company_id, model.storage_identifier)
        preprocessor = bundle.get("preprocessor")
        estimator = bundle.get("estimator")
        task_type = bundle.get("task_type", "regression")
        inference_feature_cols = bundle.get("inference_feature_columns") or bundle.get("feature_columns") or []
        classes = bundle.get("classes")
        class_to_idx = bundle.get("class_to_idx")

        # 3. Align and validate input features
        df = input_df.copy()

        # Fill any missing required inference columns with neutral defaults (0 or 'unknown')
        for col in inference_feature_cols:
            if col not in df.columns:
                # If it's a lag or rolling feature that wasn't supplied directly, fill with 0.0
                if any(x in col for x in ["_lag_", "_rolling_", "_day_", "_month_", "_dow_"]):
                    df[col] = 0.0
                else:
                    df[col] = np.nan

        # Select only required columns in strict order
        X_df = df[inference_feature_cols].copy()

        # 4. Transform via preprocessor pipeline
        try:
            X_proc = preprocessor.transform(X_df)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Preprocessing failed on input data: {str(e)}",
            )

        # 5. Model Inference
        probabilities = None
        anomaly_scores = None

        if task_type in ["regression", "forecasting"]:
            raw_preds = estimator.predict(X_proc)
            preds = [float(p) for p in raw_preds]
        elif task_type == "classification":
            raw_preds = estimator.predict(X_proc)
            if hasattr(estimator, "predict_proba"):
                try:
                    prob_matrix = estimator.predict_proba(X_proc)
                    probabilities = [[float(round(p, 4)) for p in row] for row in prob_matrix]
                except Exception:
                    probabilities = None

            # Map back to original class label if indices were used (e.g. XGBoost)
            if classes is not None and len(classes) > 0:
                idx_to_class = {i: c for i, c in enumerate(classes)}
                preds = [
                    idx_to_class.get(p, str(p)) if isinstance(p, (int, np.integer)) else str(p)
                    for p in raw_preds
                ]
            else:
                preds = [str(p) for p in raw_preds]
        elif task_type == "anomaly":
            raw_labels = estimator.predict(X_proc)  # -1 is anomaly, 1 is normal
            preds = ["anomaly" if l == -1 else "normal" for l in raw_labels]
            if hasattr(estimator, "decision_function"):
                scores = -estimator.decision_function(X_proc)
                anomaly_scores = [float(round(s, 4)) for s in scores]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported task type: {task_type}",
            )

        latency_ms = round((time.time() - start_time) * 1000, 2)

        # 6. Build response payload
        results: List[Dict[str, Any]] = []
        for i in range(len(df)):
            item: Dict[str, Any] = {
                "row_index": i,
                "prediction": preds[i],
            }
            if probabilities is not None and i < len(probabilities):
                item["probabilities"] = probabilities[i]
                if classes is not None:
                    item["class_labels"] = list(classes)
            if anomaly_scores is not None and i < len(anomaly_scores):
                item["anomaly_score"] = anomaly_scores[i]
            results.append(item)

        # 7. Persist prediction log
        log_entry = PredictionLog(
            company_id=company_id,
            model_id=model_id,
            dataset_id=model.dataset_id,
            prediction_type=prediction_type,
            row_count=len(df),
            input_sample=input_df.head(3).to_dict(orient="records"),
            output_sample=results[:3],
            latency_ms=latency_ms,
        )
        db.add(log_entry)
        db.commit()

        return {
            "prediction_id": log_entry.id,
            "model_id": model_id,
            "algorithm": model.algorithm,
            "algorithm_display_name": model.algorithm_display_name,
            "task_type": task_type,
            "total_rows": len(df),
            "latency_ms": latency_ms,
            "predictions": results,
            "classes": list(classes) if classes is not None else None,
        }


prediction_service = PredictionService()
