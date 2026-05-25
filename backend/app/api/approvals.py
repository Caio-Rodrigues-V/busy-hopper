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
    res = await db.execute(select(Approval).filter(Approval.id == approval_id, Approval.company_id == company.id))
    approval = res.scalars().first()
    if not approval:
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
    
    if decision == "approved" and task_id is not None and agent_id is not None:
        try:
            task_id = int(task_id)
            agent_id = int(agent_id)
        except (ValueError, TypeError) as te:
            logger.error(f"Failed to cast task_id {task_id} or agent_id {agent_id} to int: {te}")
            raise HTTPException(status_code=400, detail="Invalid task_id or agent_id in payload.")

        # Validate that the task and agent in the payload belong to the same company
        task_check = await db.execute(select(Task).filter(Task.id == task_id, Task.company_id == company.id))
        agent_check = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
        task_obj = task_check.scalars().first()
        agent_obj = agent_check.scalars().first()
        
        if not task_obj or not agent_obj:
            logger.error(
                f"Approval validation failed: task_id={task_id} (exists: {task_obj is not None}), "
                f"agent_id={agent_id} (exists: {agent_obj is not None}) for company_id={company.id}"
            )
            raise HTTPException(status_code=400, detail="Invalid approval payload: Agent or Task does not belong to this company.")

        logger.info(f"Approvals: Resuming task {task_id} run for Agent {agent_id} in background.")
        background_tasks.add_task(background_resume_run, company.id, agent_id, task_id, approval.id)
        
    return approval
