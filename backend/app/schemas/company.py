from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CompanyBase(BaseModel):
    name: str
    mission: str
    monthly_budget_usd: Optional[float] = Field(default=100.0, gt=0.0)
    markup_pct: Optional[float] = Field(default=20.0, ge=0.0) # 20% markup by default

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    mission: Optional[str] = None
    monthly_budget_usd: Optional[float] = Field(default=None, gt=0.0)
    markup_pct: Optional[float] = Field(default=None, ge=0.0)

class CompanyResponse(CompanyBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
