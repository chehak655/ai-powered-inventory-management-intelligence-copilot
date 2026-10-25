import io
from typing import List, Optional
import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    UploadFile,
    File,
    Response,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import WorkspaceContext, get_current_workspace
from app.models.training import CandidateModel
from app.models.prediction import PredictionLog
from app.schemas.prediction import (
    SinglePredictionRequest,
    BatchPredictionRequest,
    PredictionResponse,
    PredictionLogResponse,
)
from app.services.ml.prediction_service import prediction_service

router = APIRouter(prefix="/predictions", tags=["Predictions Engine"])


def resolve_model_id(db: Session, company_id: str, model_id: Optional[str], dataset_id: Optional[str]) -> str:
    """Resolve explicit model ID or find the active production model for the given dataset."""
    if model_id:
        return model_id

    if not dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either model_id or dataset_id.",
        )

    active_model = (
        db.query(CandidateModel)
        .filter(
            CandidateModel.company_id == company_id,
            CandidateModel.dataset_id == dataset_id,
            CandidateModel.is_active == True,
            CandidateModel.status == "SUCCESS",
        )
        .first()
    )
    if not active_model:
        # Fall back to latest successful candidate model
        latest_model = (
            db.query(CandidateModel)
            .filter(
                CandidateModel.company_id == company_id,
                CandidateModel.dataset_id == dataset_id,
                CandidateModel.status == "SUCCESS",
            )
            .order_by(CandidateModel.created_at.desc())
            .first()
        )
        if not latest_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No trained or active models found for this dataset.",
            )
        return latest_model.id

    return active_model.id


@router.post(
    "/single",
    response_model=PredictionResponse,
    summary="Generate real-time prediction for a single record",
)
def predict_single(
    payload: SinglePredictionRequest,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Execute prediction on a single feature record using active or specified model."""
    target_model_id = resolve_model_id(db, ctx.company.id, payload.model_id, payload.dataset_id)
    input_df = pd.DataFrame([payload.inputs])

    res = prediction_service.execute_prediction(
        db=db,
        company_id=ctx.company.id,
        model_id=target_model_id,
        input_df=input_df,
        prediction_type="single",
    )
    return res


@router.post(
    "/batch",
    response_model=PredictionResponse,
    summary="Generate predictions for a list of records (JSON)",
)
def predict_batch(
    payload: BatchPredictionRequest,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Execute batch inference across an array of records."""
    if not payload.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Records array cannot be empty.",
        )

    target_model_id = resolve_model_id(db, ctx.company.id, payload.model_id, payload.dataset_id)
    input_df = pd.DataFrame(payload.records)

    res = prediction_service.execute_prediction(
        db=db,
        company_id=ctx.company.id,
        model_id=target_model_id,
        input_df=input_df,
        prediction_type="batch",
    )
    return res


@router.post(
    "/batch-file",
    summary="Upload CSV file, run batch inference, and download enriched CSV with predictions",
)
async def predict_batch_file(
    file: UploadFile = File(...),
    model_id: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Upload a CSV dataset for inference; returns a downloadable CSV with predicted values appended."""
    target_model_id = resolve_model_id(db, ctx.company.id, model_id, dataset_id)

    file_bytes = await file.read()
    try:
        if file.filename and file.filename.endswith(".xlsx"):
            input_df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            input_df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse uploaded file: {str(e)}",
        )

    if input_df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    res = prediction_service.execute_prediction(
        db=db,
        company_id=ctx.company.id,
        model_id=target_model_id,
        input_df=input_df,
        prediction_type="batch",
    )

    # Append prediction column to the dataframe
    output_df = input_df.copy()
    preds = [item["prediction"] for item in res["predictions"]]
    output_df["predicted_value"] = preds

    if "probabilities" in res["predictions"][0]:
        output_df["prediction_confidence"] = [
            max(item["probabilities"]) if item.get("probabilities") else None
            for item in res["predictions"]
        ]

    # Convert to CSV buffer
    csv_buf = io.StringIO()
    output_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=predictions_{file.filename or 'batch.csv'}"
        },
    )


@router.get(
    "/history",
    response_model=List[PredictionLogResponse],
    summary="Get prediction execution history for workspace",
)
def get_prediction_history(
    limit: int = Query(20, ge=1, le=100),
    model_id: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """Retrieve historical prediction requests, latency, and sample inputs/outputs."""
    query = db.query(PredictionLog).filter(PredictionLog.company_id == ctx.company.id)
    if model_id:
        query = query.filter(PredictionLog.model_id == model_id)
    if dataset_id:
        query = query.filter(PredictionLog.dataset_id == dataset_id)

    logs = query.order_by(PredictionLog.created_at.desc()).limit(limit).all()
    return [PredictionLogResponse.model_validate(l) for l in logs]
