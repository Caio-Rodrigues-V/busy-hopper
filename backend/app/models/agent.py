from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    role_prompt = Column(String, nullable=False)
    boss_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    adapter_type = Column(String, nullable=False) # e.g. "claude", "http", "bash"
    model = Column(String, nullable=False, default="claude-3-5-sonnet-20241022")
    temperature = Column(Float, default=0.0)
    tools = Column(JSON, nullable=False, default=list) # JSON list e.g. ["delegate_task", "request_approval"]
    monthly_budget_usd = Column(Float, default=50.0)
    status = Column(String, default="active") # active, paused, exhausted
    heartbeat_cron = Column(String, nullable=True) # cron string (e.g. "*/5 * * * *")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="agents")
    # Self-referencing boss-subordinate relation
    boss = relationship("Agent", remote_side=[id], backref="subordinates")
    tasks = relationship("Task", back_populates="assignee")
    runs = relationship("Run", back_populates="agent")
