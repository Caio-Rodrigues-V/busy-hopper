from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TaskBase(BaseModel):
    title: str
    description: str
    status: str = "todo" # "todo", "in_progress", "done", "failed", "paused"
    assignee_agent_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    traces_to_goal: bool = True

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assignee_agent_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    traces_to_goal: Optional[bool] = None
    locked_at: Optional[datetime] = None

class TaskResponse(TaskBase):
    id: int
    company_id: int
    created_at: datetime
    locked_at: Optional[datetime] = None

    class Config:
        from_attributes = True
