from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    BackgroundTasks,
    Request,
)
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.dependencies import (
    WorkspaceContext,
    get_client_ip,
    get_current_workspace,
)
from app.models.dataset import Dataset, DatasetConfiguration
from app.models.training import TrainingRun, CandidateModel
from app.schemas.training import (
    StartTrainingRequest,
    TrainingRunResponse,
    TrainingRunStatusResponse,
    CandidateModelResponse,
    ModelComparisonResponse,
)
from app.services.ml.orchestrator import run_training_pipeline
from app.services.dataset_service import suggest_default_configuration, validate_dataset_configuration
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/training", tags=["Machine Learning Training"])


def background_training_task(run_id: str):
    """Background task worker with its own database session."""
    db = SessionLocal()
    try:
        run_training_pipeline(db, run_id)
    finally:
        db.close()


@router.post(
    "/start",
    response_model=TrainingRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start training candidate machine learning models asynchronously",
)
def start_training_run(
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Launch asynchronous machine learning training run on authorized dataset.
    Validates configuration, prevents duplicate submissions, and trains candidate models in background.
    """
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == request.dataset_id,
            Dataset.company_id == ctx.company.id,
            Dataset.is_deleted == False,
        )
        .first()
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found in this company workspace.",
        )

    # Prevent concurrent duplicate submissions on same dataset
    active_run = (
        db.query(TrainingRun)
        .filter(
            TrainingRun.dataset_id == dataset.id,
            TrainingRun.company_id == ctx.company.id,
            TrainingRun.status.in_(["QUEUED", "RUNNING"]),
        )
        .first()
    )
    if active_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A training run ({active_run.id}) is already in progress for this dataset.",
        )

    # Retrieve or generate column configuration
    config = (
        db.query(DatasetConfiguration)
        .filter(
            DatasetConfiguration.dataset_id == dataset.id,
            DatasetConfiguration.company_id == ctx.company.id,
        )
        .order_by(DatasetConfiguration.configuration_version.desc())
        .first()
    )

    if not config:
        # Auto-generate default configuration if user hasn't explicitly saved one
        if not dataset.schema_metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset has not been profiled. Please configure columns before training.",
            )
        default_sugg = suggest_default_configuration(dataset.schema_metadata)
        config = DatasetConfiguration(
            company_id=ctx.company.id,
            dataset_id=dataset.id,
            task_type=request.task_type or default_sugg["recommended_task"],
            target_column=default_sugg["target_column"],
            feature_columns=default_sugg["feature_columns"],
            date_column=default_sugg["date_column"],
            entity_columns=default_sugg["entity_columns"],
            excluded_columns=default_sugg["excluded_columns"],
            configuration_version=1,
        )
        db.add(config)
        db.flush()

    task_type = request.task_type or config.task_type
    objective = (
        request.objective
        if request.objective
        else ("macro_f1" if task_type == "classification" else "observed_anomaly_pct" if task_type == "anomaly" else "rmse")
    )

    # Inspect dataset configuration validation
    validation = validate_dataset_configuration(
        profile=dataset.schema_metadata,
        task_type=task_type,
        target_column=config.target_column,
        feature_columns=config.feature_columns,
        date_column=config.date_column,
        entity_columns=config.entity_columns,
    )
    if not validation["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation["warnings"][0] if validation["warnings"] else "Invalid dataset configuration.",
        )

    # Create TrainingRun record
    run = TrainingRun(
        company_id=ctx.company.id,
        dataset_id=dataset.id,
        task_type=task_type,
        status="QUEUED",
        target_column=config.target_column,
        feature_columns=config.feature_columns,
        date_column=config.date_column,
        entity_columns=config.entity_columns,
        configuration={
            "task_type": task_type,
            "target_column": config.target_column,
            "feature_columns": config.feature_columns,
            "date_column": config.date_column,
            "entity_columns": config.entity_columns,
            "objective": objective,
            "validation_warnings": validation.get("warnings", []),
            "target_recommendation": validation.get("recommendation"),
            "target_diagnostics": validation.get("target_diagnostics", {}),
        },
        split_strategy="chronological" if task_type == "forecasting" else "stratified" if task_type == "classification" else "random",
    )
    db.add(run)

    ip_addr = get_client_ip(raw_request)
    log_audit_event(
        db=db,
        action="TRAINING_RUN_STARTED",
        resource_type="training_run",
        company_id=ctx.company.id,
        user_id=ctx.user.id,
        resource_id=dataset.id,
        details={"task_type": task_type, "target": config.target_column},
        ip_address=ip_addr,
    )

    db.commit()
    db.refresh(run)

    # Launch background job
    background_tasks.add_task(background_training_task, run.id)

    return TrainingRunResponse.model_validate(run)


@router.get(
    "/runs",
    response_model=List[TrainingRunResponse],
    summary="List training runs for company workspace",
)
def list_training_runs(
    dataset_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve historical training runs for active company workspace."""
    query = db.query(TrainingRun).filter(TrainingRun.company_id == ctx.company.id)
    if dataset_id:
        query = query.filter(TrainingRun.dataset_id == dataset_id)

    runs = query.order_by(TrainingRun.created_at.desc()).limit(limit).all()
    return [TrainingRunResponse.model_validate(r) for r in runs]


@router.get(
    "/runs/{run_id}",
    response_model=TrainingRunResponse,
    summary="Get training run details with candidate models",
)
def get_training_run(
    run_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve training run details and all candidate models. Strictly verifies company isolation."""
    run = (
        db.query(TrainingRun)
        .filter(TrainingRun.id == run_id, TrainingRun.company_id == ctx.company.id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training run not found in this company workspace.",
        )

    resp = TrainingRunResponse.model_validate(run)
    resp.models = [CandidateModelResponse.model_validate(m) for m in run.candidate_models]
    return resp


@router.get(
    "/runs/{run_id}/status",
    response_model=TrainingRunStatusResponse,
    summary="Quick status check for polling training runs",
)
def get_training_run_status(
    run_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Check current status and duration of a training run."""
    run = (
        db.query(TrainingRun)
        .filter(TrainingRun.id == run_id, TrainingRun.company_id == ctx.company.id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training run not found in this company workspace.",
        )

    return TrainingRunStatusResponse(
        id=run.id,
        status=run.status,
        task_type=run.task_type,
        candidate_count=run.candidate_count,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
    )


@router.get(
    "/runs/{run_id}/comparison",
    response_model=ModelComparisonResponse,
    summary="Get comparison-ready metrics table and visualizations",
)
def get_model_comparison(
    run_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Retrieve ranked candidate models with metrics formatted for charts and tables.
    Ranks by primary task metric (RMSE/MAE for regression/forecasting, F1/Accuracy for classification).
    """
    run = (
        db.query(TrainingRun)
        .filter(TrainingRun.id == run_id, TrainingRun.company_id == ctx.company.id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training run not found in this company workspace.",
        )

    candidates = (
        db.query(CandidateModel)
        .filter(
            CandidateModel.training_run_id == run.id,
            CandidateModel.company_id == ctx.company.id,
        )
        .all()
    )

    models_data = [CandidateModelResponse.model_validate(m) for m in candidates]

    # Primary metric determination & ranking
    config = run.configuration or {}
    configured_obj = config.get("objective")
    
    primary_metric = "rmse"
    primary_metric_direction = "lower_is_better"
    primary_metric_display_name = "Root Mean Squared Error (RMSE)"
    is_unsupervised = False

    if run.task_type in ["regression", "forecasting"]:
        if configured_obj and configured_obj.lower() == "mae":
            primary_metric = "mae"
            primary_metric_display_name = "Mean Absolute Error (MAE)"
        else:
            primary_metric = "rmse"
            primary_metric_display_name = "Root Mean Squared Error (RMSE)"
        primary_metric_direction = "lower_is_better"

        # Sort ascending by primary metric (lower error is better)
        models_data.sort(
            key=lambda m: (
                m.status != "SUCCESS",
                m.metrics.get(primary_metric) if m.metrics and m.metrics.get(primary_metric) is not None else float("inf"),
            )
        )
    elif run.task_type == "classification":
        primary_metric = "macro_f1"
        primary_metric_display_name = "Macro F1-Score"
        primary_metric_direction = "higher_is_better"
        # Sort descending by Macro F1 (higher is better)
        models_data.sort(
            key=lambda m: (
                m.status != "SUCCESS",
                -(m.metrics.get("macro_f1") if m.metrics and m.metrics.get("macro_f1") is not None else (m.metrics.get("f1") if m.metrics and m.metrics.get("f1") is not None else -1)),
            )
        )
    elif run.task_type == "anomaly":
        primary_metric = "observed_anomaly_pct"
        primary_metric_display_name = "Observed Anomaly Rate (%)"
        primary_metric_direction = "diagnostic"
        is_unsupervised = True
        # In unsupervised anomaly detection, metrics are diagnostic indicators, not a competitive accuracy rank
        models_data.sort(
            key=lambda m: (
                m.status != "SUCCESS",
                m.algorithm,
            )
        )

    return ModelComparisonResponse(
        run_id=run.id,
        task_type=run.task_type,
        target_column=run.target_column,
        date_column=run.date_column,
        primary_metric=primary_metric,
        primary_metric_direction=primary_metric_direction,
        primary_metric_display_name=primary_metric_display_name,
        is_unsupervised=is_unsupervised,
        task_objective=configured_obj or primary_metric,
        metrics_table=models_data,
    )


@router.get(
    "/models/{model_id}",
    response_model=CandidateModelResponse,
    summary="Get single candidate model details and diagnostics",
)
def get_candidate_model(
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
    "/models/{model_id}/activate",
    response_model=CandidateModelResponse,
    summary="Set candidate model as active production model for its dataset",
)
def activate_model(
    model_id: str,
    raw_request: Request,
    require_beats_baseline: bool = Query(False, description="Strictly forbid activation if model is worse than baseline"),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Promote a trained candidate model to be the active production model for its dataset.
    Deactivates any previous active model for this dataset within the company workspace.
    Compares against baseline on the configured objective and issues warnings if subpar.
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
            detail="Cannot activate a failed model.",
        )

    # Verify baseline comparison on configured primary metric
    metrics = model.metrics or {}
    r2_val = metrics.get("r2")
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

    # Deactivate any currently active model for this dataset
    db.query(CandidateModel).filter(
        CandidateModel.dataset_id == model.dataset_id,
        CandidateModel.company_id == ctx.company.id,
        CandidateModel.is_active == True,
    ).update({"is_active": False})

    # Activate this model
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
