from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import WorkspaceContext, get_current_workspace, get_client_ip
from app.models.training import CandidateModel, TrainingRun
from app.models.dataset import Dataset
from app.schemas.training import CandidateModelResponse
from app.services.ml.prediction_service import prediction_service
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/models", tags=["Model Registry"])


@router.get(
    "/",
    response_model=List[CandidateModelResponse],
    summary="List candidate and active models for company workspace",
)
def list_models(
    dataset_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    task_type: Optional[str] = Query(None),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve models trained within this workspace, with optional filtering by dataset or active status."""
    query = db.query(CandidateModel).filter(CandidateModel.company_id == ctx.company.id)

    if dataset_id:
        query = query.filter(CandidateModel.dataset_id == dataset_id)
    if is_active is not None:
        query = query.filter(CandidateModel.is_active == is_active)
    if task_type:
        query = query.join(CandidateModel.training_run).filter(TrainingRun.task_type == task_type)

    models = query.order_by(CandidateModel.is_active.desc(), CandidateModel.created_at.desc()).all()
    return [CandidateModelResponse.model_validate(m) for m in models]


@router.get(
    "/{model_id}",
    response_model=CandidateModelResponse,
    summary="Get model details and performance metrics",
)
def get_model(
    model_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve full candidate model evaluation metrics, sample predictions, and feature importances."""
    model = (
        db.query(CandidateModel)
        .filter(
            CandidateModel.id == model_id,
            CandidateModel.company_id == ctx.company.id,
        )
        .first()
    )
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in this company workspace.",
        )
    return CandidateModelResponse.model_validate(model)


@router.post(
    "/{model_id}/activate",
    response_model=CandidateModelResponse,
    summary="Set model as active production model",
)
def activate_model_in_registry(
    model_id: str,
    raw_request: Request,
    require_beats_baseline: bool = Query(False, description="Strictly forbid activation if model is worse than baseline"),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Promote a candidate model to active production status for its dataset.
    Enforces validity checks: completed run, loadable artifact with valid estimator,
    compatible input schema, and finite metrics.
    Warns when a candidate performs worse than its baseline.
    """
    model = (
        db.query(CandidateModel)
        .filter(
            CandidateModel.id == model_id,
            CandidateModel.company_id == ctx.company.id,
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
            detail="Cannot activate a model with failed training status.",
        )

    # 1. Verify training run status
    run = model.training_run
    if run and run.status not in ["COMPLETED", "PARTIALLY_FAILED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot activate model from an incomplete training run ({run.status}).",
        )

    # 2. Verify model artifact exists and is loadable
    if not model.storage_identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model artifact missing from storage.",
        )
    try:
        artifact = prediction_service.load_model_artifact(ctx.company.id, model.storage_identifier)
        if "estimator" not in artifact:
            raise ValueError("Artifact does not contain a fitted estimator.")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model artifact verification failed: {str(e)}",
        )

    # 3. Verify finite evaluation metrics
    metrics = model.metrics or {}
    r2_val = metrics.get("r2")
    if r2_val is not None and not isinstance(r2_val, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model has non-finite evaluation metrics.",
        )

    # 4. Check baseline performance comparison on configured primary metric
    eval_summary = dict(model.evaluation_summary or {})
    baseline_comp = eval_summary.get("baseline_comparison") or {}
    beats_baseline = baseline_comp.get("beats_baseline")
    
    run = model.training_run
    task_type = run.task_type if run else "regression"
    configured_obj = (run.configuration or {}).get("objective") if run else None
    primary_metric = configured_obj or baseline_comp.get("primary_metric", "rmse" if task_type in ["regression", "forecasting"] else "macro_f1")

    is_subpar = False
    subpar_reason = ""

    if task_type in ["regression", "forecasting"]:
        if beats_baseline is False:
            is_subpar = True
            subpar_reason = f"Candidate model failed to outperform baseline on configured primary metric ({primary_metric})."
        elif beats_baseline is True and r2_val is not None and r2_val < 0.0:
            # Consistent with task objective: Do not block promotion solely because R² is slightly negative
            # when explicitly selected business metric (e.g. MAE or RMSE) justifies the choice
            eval_summary["r2_advisory"] = (
                f"Advisory: Model R² ({r2_val:.4f}) is negative, but model outperforms baseline on configured objective ({primary_metric})."
            )
            model.evaluation_summary = eval_summary
        elif beats_baseline is None and r2_val is not None and r2_val < 0.0:
            is_subpar = True
            subpar_reason = f"Model R² ({r2_val}) is negative and no baseline superiority was established."
    elif task_type == "classification":
        if beats_baseline is False:
            is_subpar = True
            subpar_reason = "Candidate model failed to outperform baseline on Macro F1-Score."

    if is_subpar and require_beats_baseline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Promotion blocked under strict policy: {subpar_reason}",
        )

    if is_subpar:
        eval_summary["activation_warning"] = (
            f"Warning: {subpar_reason} User exercised explicit promotion authority."
        )
        model.evaluation_summary = eval_summary

    # Deactivate other models for the same dataset
    db.query(CandidateModel).filter(
        CandidateModel.dataset_id == model.dataset_id,
        CandidateModel.company_id == ctx.company.id,
        CandidateModel.is_active == True,
    ).update({"is_active": False})

    model.is_active = True
    db.commit()
    db.refresh(model)

    ip_addr = get_client_ip(raw_request)
    log_audit_event(
        db=db,
        action="MODEL_ACTIVATED",
        resource_type="candidate_model",
        company_id=ctx.company.id,
        user_id=ctx.user.id,
        resource_id=model.id,
        details={
            "algorithm": model.algorithm,
            "dataset_id": model.dataset_id,
            "is_subpar": is_subpar,
            "subpar_reason": subpar_reason if is_subpar else None,
            "beats_baseline": beats_baseline,
        },
        ip_address=ip_addr,
    )
    db.commit()

    return CandidateModelResponse.model_validate(model)


@router.get(
    "/{model_id}/schema",
    summary="Get input feature schema required for inference",
)
def get_model_schema(
    model_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Retrieve required and optional input columns, data types, and default values
    needed to execute predictions with this model.
    """
    model = (
        db.query(CandidateModel)
        .filter(
            CandidateModel.id == model_id,
            CandidateModel.company_id == ctx.company.id,
        )
        .first()
    )
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in this company workspace.",
        )

    bundle = prediction_service.load_model_artifact(ctx.company.id, model.storage_identifier)
    run: TrainingRun = model.training_run
    dataset: Dataset = model.dataset

    # Get sample column values from dataset profile if available
    column_profiles = {}
    if dataset and dataset.schema_metadata and "columns" in dataset.schema_metadata:
        for col_p in dataset.schema_metadata["columns"]:
            column_profiles[col_p["name"]] = col_p

    feature_cols = bundle.get("feature_columns") or (run.feature_columns if run else [])
    num_cols = bundle.get("num_cols") or []
    cat_cols = bundle.get("cat_cols") or []

    prep = bundle.get("preprocessor")
    if hasattr(prep, "final_numeric_cols"):
        num_cols = prep.final_numeric_cols
        cat_cols = prep.final_categorical_cols

    fields = []
    for col in feature_cols:
        col_type = "numeric" if col in num_cols else "categorical" if col in cat_cols else "text"
        profile = column_profiles.get(col, {})
        fields.append({
            "name": col,
            "type": col_type,
            "sample_values": profile.get("sample_values", [])[:5],
            "default": profile.get("numeric_stats", {}).get("mean") if col_type == "numeric" else (profile.get("sample_values", [None])[0] if profile.get("sample_values") else None),
        })

    return {
        "model_id": model.id,
        "algorithm": model.algorithm,
        "algorithm_display_name": model.algorithm_display_name,
        "task_type": bundle.get("task_type", run.task_type if run else "regression"),
        "target_column": bundle.get("target_column"),
        "fields": fields,
        "classes": bundle.get("classes"),
    }
