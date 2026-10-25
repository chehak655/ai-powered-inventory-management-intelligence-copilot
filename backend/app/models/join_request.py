import enum
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Enum as SQLEnum, DateTime, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import generate_uuid, TimestampMixin


class JoinRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkspaceJoinRequest(Base, TimestampMixin):
    __tablename__ = "workspace_join_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    status = Column(SQLEnum(JoinRequestStatus, native_enum=False, length=20), default=JoinRequestStatus.PENDING, nullable=False, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Relationships
    company = relationship("Company", backref="join_requests")
    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_id])

    def __repr__(self) -> str:
        return f"<WorkspaceJoinRequest id={self.id} company_id={self.company_id} user_id={self.user_id} status={self.status}>"
