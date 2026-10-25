from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import generate_uuid, TimestampMixin


class TrainingRun(Base, TimestampMixin):
    __tablename__ = "training_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # regression, forecasting, classification, anomaly
    status = Column(String(50), default="QUEUED", nullable=False, index=True)  # QUEUED, RUNNING, COMPLETED, PARTIALLY_FAILED, FAILED, CANCELLED
    
    target_column = Column(String(255), nullable=True)
    feature_columns = Column(JSON, nullable=False)
    date_column = Column(String(255), nullable=True)
    entity_columns = Column(JSON, nullable=True)
    configuration = Column(JSON, nullable=True)
    
    split_strategy = Column(String(50), default="chronological", nullable=True)
    train_row_count = Column(Integer, default=0, nullable=False)
    val_row_count = Column(Integer, default=0, nullable=False)
    val_time_range = Column(JSON, nullable=True)
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0, nullable=False)
    error_message = Column(String(1000), nullable=True)
    candidate_count = Column(Integer, default=0, nullable=False)

    # Relationships
    company = relationship("Company", backref="training_runs")
    dataset = relationship("Dataset", backref="training_runs")
    candidate_models = relationship("CandidateModel", back_populates="training_run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<TrainingRun id={self.id} task={self.task_type} status={self.status}>"


class CandidateModel(Base, TimestampMixin):
    __tablename__ = "candidate_models"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    training_run_id = Column(String(36), ForeignKey("training_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    
    algorithm = Column(String(100), nullable=False, index=True)
    algorithm_display_name = Column(String(150), nullable=False)
    model_family = Column(String(50), nullable=False)  # baseline, linear, tree, ensemble, anomaly
    status = Column(String(50), default="SUCCESS", nullable=False)  # SUCCESS, FAILED
    
    hyperparameters = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)  # mae, rmse, wape, r2, accuracy, precision, recall, f1, etc.
    evaluation_summary = Column(JSON, nullable=True)
    sample_predictions = Column(JSON, nullable=True)  # [{actual, predicted, residual}]
    feature_importances = Column(JSON, nullable=True)
    
    storage_identifier = Column(String(500), nullable=True)
    artifact_size_bytes = Column(Integer, default=0, nullable=False)
    error_details = Column(String(1000), nullable=True)
    training_duration_seconds = Column(Float, default=0.0, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    training_run = relationship("TrainingRun", back_populates="candidate_models")
    company = relationship("Company", backref="candidate_models")
    dataset = relationship("Dataset", backref="candidate_models")

    def __repr__(self) -> str:
        return f"<CandidateModel id={self.id} algorithm={self.algorithm} status={self.status}>"
