from pydantic import BaseModel
from datetime import datetime

class ApiCredentialBase(BaseModel):
    provider: str # e.g. "anthropic"

class ApiCredentialCreate(ApiCredentialBase):
    api_key: str

class ApiCredentialResponse(ApiCredentialBase):
    id: int
    company_id: int
    last4: str
    created_at: datetime

    class Config:
        from_attributes = True
