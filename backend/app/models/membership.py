import enum
from sqlalchemy import Column, String, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import generate_uuid, TimestampMixin


class MemberRole(str, enum.Enum):
    OWNER = "OWNER"
    WORKER = "WORKER"


class CompanyMember(Base, TimestampMixin):
    __tablename__ = "company_members"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(MemberRole, native_enum=False, length=20), default=MemberRole.WORKER, nullable=False)

    # Relationships
    company = relationship("Company", back_populates="members")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_user_membership"),
    )

    def __repr__(self) -> str:
        return f"<CompanyMember id={self.id} company_id={self.company_id} user_id={self.user_id} role={self.role}>"
