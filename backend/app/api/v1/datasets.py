import math
from typing import Optional, List
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    HTTPException,
    status,
    Query,
    Request,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    WorkspaceContext,
    get_client_ip,
    get_current_workspace,
    require_owner,
)
from app.models.dataset import Dataset, DatasetVersion, DatasetConfiguration
from app.schemas.dataset import (
    DatasetResponse,
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetPreviewResponse,
    SuggestedConfigResponse,
    DatasetConfigurationRequest,
    DatasetConfigurationResponse,
    ValidateConfigurationRequest,
    ValidateConfigurationResponse,
)
from app.services.storage import storage_service
from app.services.dataset_service import (
    compute_sha256,
    parse_dataset_bytes,
    profile_dataset,
    suggest_default_configuration,
    get_paginated_preview,
    validate_dataset_configuration,
)
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/datasets", tags=["Datasets"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB limit


@router.post(
    "/upload",
    response_model=DatasetDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and profile a CSV or Excel dataset",
)
async def upload_dataset(
    raw_request: Request,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Securely upload, validate, parse, profile, and persist a CSV or Excel dataset.
    Preserves company isolation and generates server-controlled storage identifiers.
    """
    filename = file.filename or "dataset.csv"
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    if ext not in ["csv", "xlsx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '.{ext}'. Supported formats: .csv, .xlsx",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    # Compute checksum
    checksum = compute_sha256(content)

    # Parse and profile in working memory
    df = parse_dataset_bytes(content, filename)
    profile = profile_dataset(df)

    # Save to company-isolated filesystem storage
    storage_identifier = storage_service.save_file(
        company_id=ctx.company.id,
        content=content,
        extension=ext,
        subfolder="datasets",
    )

    try:
        # Create dataset metadata record
        display_name = name.strip() if name and name.strip() else filename
        dataset = Dataset(
            company_id=ctx.company.id,
            uploader_id=ctx.user.id,
            name=display_name,
            original_filename=filename,
            storage_identifier=storage_identifier,
            file_format=ext,
            file_size_bytes=len(content),
            checksum_sha256=checksum,
            row_count=profile["summary"]["row_count"],
            column_count=profile["summary"]["column_count"],
            processing_status="ready",
            validation_summary=profile["summary"],
            schema_metadata=profile,
            is_deleted=False,
        )
        db.add(dataset)
        db.flush()

        # Create initial immutable version
        dataset_version = DatasetVersion(
            dataset_id=dataset.id,
            version_num=1,
            storage_identifier=storage_identifier,
            checksum_sha256=checksum,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            schema_metadata=profile,
        )
        db.add(dataset_version)

        # Audit log
        ip_addr = get_client_ip(raw_request)
        log_audit_event(
            db=db,
            action="DATASET_UPLOADED",
            resource_type="dataset",
            company_id=ctx.company.id,
            user_id=ctx.user.id,
            resource_id=dataset.id,
            details={
                "name": dataset.name,
                "rows": dataset.row_count,
                "columns": dataset.column_count,
                "format": dataset.file_format,
            },
            ip_address=ip_addr,
        )

        db.commit()
        db.refresh(dataset)

        resp = DatasetDetailResponse.model_validate(dataset)
        resp.profile = profile
        return resp

    except Exception as e:
        db.rollback()
        # Clean up stored file to prevent orphaned storage
        storage_service.delete_file(ctx.company.id, storage_identifier)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed during dataset registration: {str(e)}",
        )


@router.get(
    "/",
    response_model=DatasetListResponse,
    summary="List datasets for active workspace with pagination",
)
def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve all datasets belonging to caller's active company workspace."""
    query = (
        db.query(Dataset)
        .filter(Dataset.company_id == ctx.company.id, Dataset.is_deleted == False)
    )

    if search:
        query = query.filter(Dataset.name.ilike(f"%{search.strip()}%"))

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = (
        query.order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DatasetListResponse(
        items=[DatasetResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
    summary="Get dataset metadata, validation summary, and profile",
)
def get_dataset(
    dataset_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Get single dataset with profiling report. Strictly verifies company ownership."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    resp = DatasetDetailResponse.model_validate(dataset)
    resp.profile = dataset.schema_metadata
    return resp


@router.get(
    "/{dataset_id}/preview",
    response_model=DatasetPreviewResponse,
    summary="Get paginated row preview of dataset",
)
def preview_dataset(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Return paginated preview records from stored file."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    file_bytes = storage_service.read_file(ctx.company.id, dataset.storage_identifier)
    df = parse_dataset_bytes(file_bytes, dataset.original_filename)
    return get_paginated_preview(df, page=page, page_size=page_size)


@router.get(
    "/{dataset_id}/suggested-config",
    response_model=SuggestedConfigResponse,
    summary="Get heuristic recommendation for task and column mapping",
)
def get_suggested_configuration(
    dataset_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Suggest likely target, task, and feature columns dynamically based on profile."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
            Dataset.company_id == ctx.company.id,
            Dataset.is_deleted == False,
        )
        .first()
    )
    if not dataset or not dataset.schema_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset profile not available.",
        )

    suggestion = suggest_default_configuration(dataset.schema_metadata)
    return SuggestedConfigResponse(**suggestion)


@router.get(
    "/{dataset_id}/configuration",
    response_model=DatasetConfigurationResponse,
    summary="Get saved task and column configuration",
)
def get_dataset_configuration(
    dataset_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve the current saved column configuration for this dataset."""
    config = (
        db.query(DatasetConfiguration)
        .filter(
            DatasetConfiguration.dataset_id == dataset_id,
            DatasetConfiguration.company_id == ctx.company.id,
        )
        .order_by(DatasetConfiguration.configuration_version.desc())
        .first()
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No configuration found for this dataset.",
        )
    return DatasetConfigurationResponse.model_validate(config)


@router.post(
    "/{dataset_id}/configuration",
    response_model=DatasetConfigurationResponse,
    summary="Save or update dataset task and column configuration",
)
def save_dataset_configuration(
    dataset_id: str,
    request: DatasetConfigurationRequest,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Validate and persist column configuration for machine learning pipeline."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    # Validate against actual dataset schema
    all_cols = [c["name"] for c in dataset.schema_metadata.get("columns", [])] if dataset.schema_metadata else []
    
    # Check features exist
    for f in request.feature_columns:
        if f not in all_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Selected feature column '{f}' does not exist in the dataset.",
            )

    # Supervised tasks require valid target
    if request.task_type in ["regression", "forecasting", "classification"]:
        if not request.target_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task '{request.task_type}' requires a target column.",
            )
        if request.target_column not in all_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Selected target column '{request.target_column}' does not exist in the dataset.",
            )
        if request.target_column in request.feature_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target column cannot also be included as a feature column.",
            )

    # Forecasting requires date column
    if request.task_type == "forecasting":
        if not request.date_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Time-series forecasting requires a valid date/time column.",
            )
        if request.date_column not in all_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Selected date column '{request.date_column}' does not exist in the dataset.",
            )
        if request.date_column in request.feature_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date column cannot also be listed as a regular feature column.",
            )
        if request.target_column and request.date_column == request.target_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date column cannot be identical to the target column.",
            )

    # Validate entity columns
    if request.entity_columns:
        for ent in request.entity_columns:
            if ent not in all_cols:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Selected entity column '{ent}' does not exist in the dataset.",
                )
        if request.target_column and request.target_column in request.entity_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target column cannot also be included as an entity/grouping column.",
            )
        if request.date_column and request.date_column in request.entity_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date column cannot also be included as an entity/grouping column.",
            )

    # Find existing config or create new
    existing_config = (
        db.query(DatasetConfiguration)
        .filter(
            DatasetConfiguration.dataset_id == dataset_id,
            DatasetConfiguration.company_id == ctx.company.id,
        )
        .order_by(DatasetConfiguration.configuration_version.desc())
        .first()
    )

    if existing_config:
        existing_config.task_type = request.task_type
        existing_config.target_column = request.target_column
        existing_config.feature_columns = request.feature_columns
        existing_config.date_column = request.date_column
        existing_config.entity_columns = request.entity_columns
        existing_config.excluded_columns = request.excluded_columns
        existing_config.configuration_version += 1
        config = existing_config
    else:
        config = DatasetConfiguration(
            company_id=ctx.company.id,
            dataset_id=dataset.id,
            task_type=request.task_type,
            target_column=request.target_column,
            feature_columns=request.feature_columns,
            date_column=request.date_column,
            entity_columns=request.entity_columns,
            excluded_columns=request.excluded_columns,
            configuration_version=1,
        )
        db.add(config)

    ip_addr = get_client_ip(raw_request)
    log_audit_event(
        db=db,
        action="DATASET_CONFIGURED",
        resource_type="dataset_configuration",
        company_id=ctx.company.id,
        user_id=ctx.user.id,
        resource_id=dataset.id,
        details={
            "task_type": request.task_type,
            "target": request.target_column,
            "features_count": len(request.feature_columns),
        },
        ip_address=ip_addr,
    )

    db.commit()
    db.refresh(config)

    # Validate target compatibility & compute diagnostics
    validation = validate_dataset_configuration(
        profile=dataset.schema_metadata,
        task_type=config.task_type,
        target_column=config.target_column,
        feature_columns=config.feature_columns,
        date_column=config.date_column,
        entity_columns=config.entity_columns,
    )

    resp = DatasetConfigurationResponse.model_validate(config)
    resp.validation_status = "warning" if validation.get("warnings") else "valid"
    resp.validation_warnings = validation.get("warnings", [])
    resp.target_recommendation = validation.get("recommendation")
    resp.target_diagnostics = validation.get("target_diagnostics", {})
    return resp


@router.post(
    "/{dataset_id}/validate-config",
    response_model=ValidateConfigurationResponse,
    summary="Validate proposed task and target configuration without saving",
)
def validate_proposed_config(
    dataset_id: str,
    request: ValidateConfigurationRequest,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Validate target compatibility, high cardinality, and class distributions
    in real-time before saving or training. Never mutates database state.
    """
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    val_res = validate_dataset_configuration(
        profile=dataset.schema_metadata,
        task_type=request.task_type,
        target_column=request.target_column,
        feature_columns=request.feature_columns or [],
        date_column=request.date_column,
        entity_columns=request.entity_columns,
    )

    return ValidateConfigurationResponse(
        is_valid=val_res["is_valid"],
        warnings=val_res["warnings"],
        recommendation=val_res["recommendation"],
        target_diagnostics=val_res["target_diagnostics"],
    )


@router.delete(
    "/{dataset_id}",
    summary="Delete a dataset (Owner only)",
)
def delete_dataset(
    dataset_id: str,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Soft delete dataset record and clean up stored file. Owner only."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    # Soft delete in database
    dataset.is_deleted = True

    # Safely remove file from disk
    storage_service.delete_file(ctx.company.id, dataset.storage_identifier)

    ip_addr = get_client_ip(raw_request)
    log_audit_event(
        db=db,
        action="DATASET_DELETED",
        resource_type="dataset",
        company_id=ctx.company.id,
        user_id=ctx.user.id,
        resource_id=dataset.id,
        details={"name": dataset.name},
        ip_address=ip_addr,
    )

    db.commit()
    return {"message": f"Dataset '{dataset.name}' was successfully deleted."}


@router.get(
    "/{dataset_id}/download",
    summary="Download original dataset file",
)
def download_dataset(
    dataset_id: str,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Download stored dataset file. Validates company ownership."""
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
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

    file_path = storage_service.get_file_path(ctx.company.id, dataset.storage_identifier)
    return FileResponse(
        path=file_path,
        filename=dataset.original_filename,
        media_type="application/octet-stream",
    )
