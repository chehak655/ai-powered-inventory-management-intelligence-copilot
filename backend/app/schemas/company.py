from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass


class CompanyResponse(CompanyBase):
    id: str
    slug: str
    role: Optional[str] = None  # Role of current querying user
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
