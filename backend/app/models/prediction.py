from sqlalchemy import Column, String, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import generate_uuid, TimestampMixin


class PredictionLog(Base, TimestampMixin):
    __tablename__ = "prediction_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id = Column(String(36), ForeignKey("candidate_models.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    prediction_type = Column(String(20), default="single", nullable=False)  # "single" or "batch"
    row_count = Column(Integer, default=1, nullable=False)
    input_sample = Column(JSON, nullable=True)
    output_sample = Column(JSON, nullable=True)
    latency_ms = Column(Float, default=0.0, nullable=False)

    # Relationships
    company = relationship("Company", backref="prediction_logs")
    model = relationship("CandidateModel", backref="prediction_logs")
    dataset = relationship("Dataset", backref="prediction_logs")

    def __repr__(self) -> str:
        return f"<PredictionLog id={self.id} model={self.model_id} rows={self.row_count}>"
