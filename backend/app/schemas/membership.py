from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.membership import MemberRole


class AddWorkerRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: MemberRole = MemberRole.WORKER


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: MemberRole
    created_at: datetime
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class UpdateRoleRequest(BaseModel):
    role: MemberRole
