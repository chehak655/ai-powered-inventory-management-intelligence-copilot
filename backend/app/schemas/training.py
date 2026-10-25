from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class StartTrainingRequest(BaseModel):
    dataset_id: str
    task_type: Optional[str] = None
    objective: Optional[str] = None  # e.g., 'rmse', 'mae', 'macro_f1'


class CandidateModelResponse(BaseModel):
    id: str
    algorithm: str
    algorithm_display_name: str
    model_family: str
    status: str
    hyperparameters: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    evaluation_summary: Optional[Dict[str, Any]] = None
    sample_predictions: Optional[List[Dict[str, Any]]] = None
    feature_importances: Optional[Dict[str, Any]] = None
    artifact_size_bytes: int
    training_duration_seconds: float
    is_active: bool
    error_details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TrainingRunResponse(BaseModel):
    id: str
    dataset_id: str
    task_type: str
    status: str
    target_column: Optional[str] = None
    feature_columns: List[str]
    date_column: Optional[str] = None
    entity_columns: Optional[List[str]] = None
    train_row_count: int
    val_row_count: int
    val_time_range: Optional[Dict[str, Any]] = None
    duration_seconds: float
    candidate_count: int
    error_message: Optional[str] = None
    created_at: datetime
    models: Optional[List[CandidateModelResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class TrainingRunStatusResponse(BaseModel):
    id: str
    status: str
    task_type: str
    candidate_count: int
    duration_seconds: float
    error_message: Optional[str] = None


class ModelComparisonResponse(BaseModel):
    run_id: str
    task_type: str
    target_column: Optional[str] = None
    date_column: Optional[str] = None
    primary_metric: str
    primary_metric_direction: Optional[str] = "lower_is_better"  # 'lower_is_better', 'higher_is_better', 'diagnostic'
    primary_metric_display_name: Optional[str] = None
    is_unsupervised: Optional[bool] = False
    task_objective: Optional[str] = None
    metrics_table: List[CandidateModelResponse]
