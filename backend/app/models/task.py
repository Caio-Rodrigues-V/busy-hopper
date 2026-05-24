from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, default="todo") # "todo", "in_progress", "done", "failed", "paused"
    assignee_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    traces_to_goal = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    locked_at = Column(DateTime, nullable=True) # Used for atomic checkout

    company = relationship("Company", back_populates="tasks")
    assignee = relationship("Agent", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], backref="subtasks")
    runs = relationship("Run", back_populates="task", cascade="all, delete-orphan")
