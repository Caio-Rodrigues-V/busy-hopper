from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CompanyBase(BaseModel):
    name: str
    mission: str
    monthly_budget_usd: Optional[float] = 100.0
    markup_pct: Optional[float] = 20.0 # 20% markup by default

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    mission: Optional[str] = None
    monthly_budget_usd: Optional[float] = None
    markup_pct: Optional[float] = None

class CompanyResponse(CompanyBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
