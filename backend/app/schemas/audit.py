from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any

class AuditLogBase(BaseModel):
    actor: str
    action: str
    payload: Optional[Any] = None

class AuditLogCreate(AuditLogBase):
    pass

class AuditLogResponse(AuditLogBase):
    id: int
    company_id: int
    created_at: datetime

    class Config:
        from_attributes = True
