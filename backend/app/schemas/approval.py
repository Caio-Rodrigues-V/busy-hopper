from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any

class ApprovalBase(BaseModel):
    action_type: str # e.g. "run_bash_command", "high_spend"
    payload: Any
    status: str = "pending" # "pending", "approved", "rejected"

class ApprovalCreate(ApprovalBase):
    pass

class ApprovalDecision(BaseModel):
    decision: str # "approved" or "rejected"

class ApprovalResponse(ApprovalBase):
    id: int
    company_id: int
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
