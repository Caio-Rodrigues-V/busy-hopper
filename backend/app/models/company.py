from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    mission = Column(String, nullable=False)
    monthly_budget_usd = Column(Float, default=100.0)
    markup_pct = Column(Float, default=20.0) # markup markup_pct, e.g., 20.0 means cost * 1.2
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="companies")
    credentials = relationship("ApiCredential", back_populates="company", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="company", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="company", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="company", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="company", cascade="all, delete-orphan")
