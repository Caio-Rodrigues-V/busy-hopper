from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any

class RunStepBase(BaseModel):
    kind: str # llm_call, tool_call, delegation, approval
    input: Optional[Any] = None
    output: Optional[Any] = None
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

class RunStepCreate(RunStepBase):
    run_id: int

class RunStepResponse(RunStepBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class RunBase(BaseModel):
    status: str = "running"
    total_tokens: int = 0
    total_cost_usd: float = 0.0

class RunCreate(BaseModel):
    task_id: int
    agent_id: int

class RunResponse(RunBase):
    id: int
    task_id: int
    agent_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    steps: List[RunStepResponse] = []

    class Config:
        from_attributes = True
