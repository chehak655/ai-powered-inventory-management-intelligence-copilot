from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import generate_uuid, TimestampMixin


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    storage_identifier = Column(String(500), nullable=False)
    file_format = Column(String(10), nullable=False)  # csv or xlsx
    file_size_bytes = Column(Integer, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False, index=True)
    row_count = Column(Integer, default=0, nullable=False)
    column_count = Column(Integer, default=0, nullable=False)
    processing_status = Column(String(50), default="ready", nullable=False)  # ready, error
    validation_summary = Column(JSON, nullable=True)
    schema_metadata = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    company = relationship("Company", backref="datasets")
    uploader = relationship("User", backref="uploaded_datasets")
    versions = relationship("DatasetVersion", back_populates="dataset", cascade="all, delete-orphan")
    configurations = relationship("DatasetConfiguration", back_populates="dataset", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name} rows={self.row_count} cols={self.column_count}>"


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    version_num = Column(Integer, default=1, nullable=False)
    storage_identifier = Column(String(500), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    row_count = Column(Integer, default=0, nullable=False)
    column_count = Column(Integer, default=0, nullable=False)
    schema_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="versions")

    def __repr__(self) -> str:
        return f"<DatasetVersion id={self.id} dataset_id={self.dataset_id} v={self.version_num}>"


class DatasetConfiguration(Base, TimestampMixin):
    __tablename__ = "dataset_configurations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # regression, forecasting, classification, anomaly
    target_column = Column(String(255), nullable=True)
    feature_columns = Column(JSON, nullable=False)  # list of strings
    date_column = Column(String(255), nullable=True)
    entity_columns = Column(JSON, nullable=True)  # list of strings (e.g. product_id, store_id)
    excluded_columns = Column(JSON, nullable=True)  # list of strings
    configuration_version = Column(Integer, default=1, nullable=False)

    # Relationships
    company = relationship("Company", backref="dataset_configurations")
    dataset = relationship("Dataset", back_populates="configurations")

    def __repr__(self) -> str:
        return f"<DatasetConfiguration id={self.id} dataset_id={self.dataset_id} task={self.task_type}>"
