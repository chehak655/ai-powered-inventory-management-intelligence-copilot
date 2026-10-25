from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class SinglePredictionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None
    inputs: Dict[str, Any]


class BatchPredictionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None
    records: List[Dict[str, Any]]


class PredictionResultItem(BaseModel):
    row_index: int
    prediction: Any
    probabilities: Optional[List[float]] = None
    class_labels: Optional[List[str]] = None
    anomaly_score: Optional[float] = None


class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    prediction_id: str
    model_id: str
    algorithm: str
    algorithm_display_name: str
    task_type: str
    total_rows: int
    latency_ms: float
    predictions: List[PredictionResultItem]
    classes: Optional[List[str]] = None


class PredictionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: str
    model_id: str
    dataset_id: Optional[str] = None
    prediction_type: str
    row_count: int
    input_sample: Optional[List[Dict[str, Any]]] = None
    output_sample: Optional[List[Dict[str, Any]]] = None
    latency_ms: float
    created_at: datetime
