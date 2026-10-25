from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.user import UserResponse
from app.schemas.company import CompanyResponse


class OwnerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    company_name: str = Field(..., min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    companies: List[CompanyResponse]


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"
