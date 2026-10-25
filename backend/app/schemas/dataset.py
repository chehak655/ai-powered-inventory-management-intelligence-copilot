from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class DatasetResponse(BaseModel):
    id: str
    name: str
    original_filename: str
    file_format: str
    file_size_bytes: int
    row_count: int
    column_count: int
    checksum_sha256: str
    processing_status: str
    validation_summary: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetDetailResponse(DatasetResponse):
    profile: Optional[Dict[str, Any]] = None


class DatasetListResponse(BaseModel):
    items: List[DatasetResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DatasetPreviewResponse(BaseModel):
    total_rows: int
    page: int
    page_size: int
    total_pages: int
    columns: List[str]
    records: List[Dict[str, Any]]


class SuggestedConfigResponse(BaseModel):
    recommended_task: str
    target_column: Optional[str] = None
    feature_columns: List[str]
    date_column: Optional[str] = None
    entity_columns: Optional[List[str]] = None
    excluded_columns: Optional[List[str]] = None


class DatasetConfigurationRequest(BaseModel):
    task_type: str = Field(..., pattern="^(regression|forecasting|classification|anomaly)$")
    target_column: Optional[str] = None
    feature_columns: List[str] = Field(..., min_length=1)
    date_column: Optional[str] = None
    entity_columns: Optional[List[str]] = None
    excluded_columns: Optional[List[str]] = None


class DatasetConfigurationResponse(BaseModel):
    id: str
    dataset_id: str
    task_type: str
    target_column: Optional[str] = None
    feature_columns: List[str]
    date_column: Optional[str] = None
    entity_columns: Optional[List[str]] = None
    excluded_columns: Optional[List[str]] = None
    configuration_version: int
    validation_status: Optional[str] = "valid"  # "valid", "warning", "invalid"
    validation_warnings: Optional[List[str]] = None
    target_recommendation: Optional[str] = None
    target_diagnostics: Optional[Dict[str, Any]] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidateConfigurationRequest(BaseModel):
    task_type: str = Field(..., pattern="^(regression|forecasting|classification|anomaly)$")
    target_column: Optional[str] = None
    feature_columns: Optional[List[str]] = None
    date_column: Optional[str] = None
    entity_columns: Optional[List[str]] = None


class ValidateConfigurationResponse(BaseModel):
    is_valid: bool
    warnings: List[str]
    recommendation: Optional[str] = None
    target_diagnostics: Optional[Dict[str, Any]] = None
