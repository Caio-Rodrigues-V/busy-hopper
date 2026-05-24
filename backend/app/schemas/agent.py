from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class AgentBase(BaseModel):
    name: str
    title: str
    role_prompt: str
    boss_agent_id: Optional[int] = None
    adapter_type: str = "claude"
    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.0
    tools: List[str] = Field(default_factory=list)
    monthly_budget_usd: float = 50.0
    status: str = "active"
    heartbeat_cron: Optional[str] = None

class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    role_prompt: Optional[str] = None
    boss_agent_id: Optional[int] = None
    adapter_type: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    tools: Optional[List[str]] = None
    monthly_budget_usd: Optional[float] = None
    status: Optional[str] = None
    heartbeat_cron: Optional[str] = None

class AgentResponse(AgentBase):
    id: int
    company_id: int
    created_at: datetime

    class Config:
        from_attributes = True
