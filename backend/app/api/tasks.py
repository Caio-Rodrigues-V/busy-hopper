from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.task import Task
from app.models.run import Run
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.schemas.run import RunResponse
from app.services.agent_executor import create_audit_entry
from app.services.scheduler import run_agent_task

router = APIRouter()

@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(select(Task).filter(Task.company_id == company.id))
    return result.scalars().all()

@router.post("/", response_model=TaskResponse)
async def create_task(
    task_in: TaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    new_task = Task(
        company_id=company.id,
        title=task_in.title,
        description=task_in.description,
        status="todo",
        assignee_agent_id=task_in.assignee_agent_id,
        parent_task_id=task_in.parent_task_id,
        traces_to_goal=task_in.traces_to_goal
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_TASK", {"title": new_task.title, "assignee_id": new_task.assignee_agent_id}
    )
    
    # If task has an assignee, trigger execution loop immediately in backend task
    if new_task.assignee_agent_id:
        background_tasks.add_task(run_agent_task, company.id, new_task.assignee_agent_id, new_task.id)
        
    return new_task

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    task = await db.get(Task, task_id)
    if not task or task.company_id != company.id:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task

@router.get("/{task_id}/runs", response_model=List[RunResponse])
async def list_task_runs(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    task = await db.get(Task, task_id)
    if not task or task.company_id != company.id:
        raise HTTPException(status_code=404, detail="Task not found.")
        
    # Query task runs with preloaded step elements
    query = select(Run).filter(Run.task_id == task_id).options(selectinload(Run.steps)).order_by(Run.started_at.desc())
    result = await db.execute(query)
    return result.scalars().all()
