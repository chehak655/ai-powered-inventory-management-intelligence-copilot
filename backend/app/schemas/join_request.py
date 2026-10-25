from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class WorkerJoinRequestSubmit(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="Full name of worker")
    email: EmailStr = Field(..., description="Worker email address")
    password: str = Field(..., min_length=6, max_length=100, description="Initial worker password")
    workspace_slug: str = Field(..., min_length=2, max_length=100, description="Workspace slug or identifier to join")


class JoinRequestResponse(BaseModel):
    id: str
    company_id: str
    company_name: str
    company_slug: Optional[str] = None
    user_id: str
    email: str
    full_name: str
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RejectJoinRequestPayload(BaseModel):
    reason: Optional[str] = Field(None, max_length=500, description="Optional explanation for rejecting the join request")
