import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.approval import Approval
from app.schemas.approval import ApprovalDecision, ApprovalResponse
from app.services.agent_executor import create_audit_entry, AgentExecutor
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()

async def background_resume_run(company_id: int, agent_id: int, task_id: int, approval_id: int):
    """Runs the resume loop in an isolated database session."""
    async with SessionLocal() as db:
        try:
            executor = AgentExecutor(db, company_id, agent_id, task_id)
            result = await executor.resume_run(approval_id)
            logger.info(f"Background resume finished for Task {task_id}: {result}")
        except Exception as e:
            logger.error(f"Error resuming run for Task {task_id} in background: {e}", exc_info=True)

@router.get("/", response_model=List[ApprovalResponse])
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(
        select(Approval)
        .filter(Approval.company_id == company.id)
        .order_by(Approval.created_at.desc())
    )
    return result.scalars().all()

@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: int,
    decision_in: ApprovalDecision,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    approval = await db.get(Approval, approval_id)
    if not approval or approval.company_id != company.id:
        raise HTTPException(status_code=404, detail="Approval request not found.")
        
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Decision has already been registered for this request.")
        
    decision = decision_in.decision.lower()
    if decision not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid decision. Must be 'approved' or 'rejected'.")
        
    approval.status = decision
    approval.decided_by = current_user.id
    approval.decided_at = datetime.utcnow()
    await db.commit()
    await db.refresh(approval)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "DECIDE_APPROVAL", {"approval_id": approval.id, "decision": decision}
    )
    
    # Resume execution if approved and context is embedded in the payload
    payload = approval.payload or {}
    task_id = payload.get("task_id")
    agent_id = payload.get("agent_id")
    
    if decision == "approved" and task_id and agent_id:
        logger.info(f"Approvals: Resuming task {task_id} run for Agent {agent_id} in background.")
        background_tasks.add_task(background_resume_run, company.id, agent_id, task_id, approval.id)
        
    return approval
