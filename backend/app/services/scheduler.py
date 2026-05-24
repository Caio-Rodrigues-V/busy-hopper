import logging
import asyncio
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import SessionLocal
from app.models.agent import Agent
from app.models.task import Task
from app.services.agent_executor import AgentExecutor

from datetime import datetime, timezone
from app.core.config import settings

logger = logging.getLogger(__name__)

async def check_pending_tasks():
    """Polls database for active agents with pending tasks and triggers execution."""
    async with SessionLocal() as db:
        try:
            # Query all tasks in 'todo' status that have an assignee agent that is active
            stmt = select(Task).join(Agent, Task.assignee_agent_id == Agent.id).filter(
                Task.status == "todo",
                Agent.status == "active",
                Task.locked_at.is_(None)
            )
            if "postgresql" in settings.DATABASE_URL:
                stmt = stmt.with_for_update(skip_locked=True)
                
            result = await db.execute(stmt)
            pending_tasks = result.scalars().all()

            claimed_tasks = []
            for task in pending_tasks:
                task.status = "in_progress"
                task.locked_at = datetime.now(timezone.utc)
                db.add(task)
                claimed_tasks.append((task.company_id, task.assignee_agent_id, task.id))
                
            await db.commit()

            for company_id, agent_id, task_id in claimed_tasks:
                logger.info(f"Scheduler: Triggering task {task_id} for Agent {agent_id}")
                # Spawn execution in a background task
                asyncio.create_task(run_agent_task(company_id, agent_id, task_id))
        except Exception as e:
            logger.error(f"Scheduler polling error: {e}", exc_info=True)

async def run_agent_task(company_id: int, agent_id: int, task_id: int):
    """Executes a single agent run in an isolated database session context."""
    async with SessionLocal() as db:
        try:
            # Re-fetch models within this session context
            executor = AgentExecutor(db, company_id, agent_id, task_id)
            result = await executor.execute_run()
            logger.info(f"Scheduler run completed for Task {task_id}. Result: {result}")
        except Exception as e:
            logger.error(f"Error executing task {task_id} in scheduler: {e}", exc_info=True)

# APScheduler instance
scheduler = AsyncIOScheduler()

def start_scheduler():
    logger.info("Initializing background heartbeats scheduler...")
    # Poll every 10 seconds
    scheduler.add_job(check_pending_tasks, "interval", seconds=10, id="agent_heartbeat_job", replace_existing=True)
    scheduler.start()

def shutdown_scheduler():
    logger.info("Shutting down background heartbeats scheduler...")
    scheduler.shutdown()

async def reap_orphan_runs(db: AsyncSession):
    """Finds runs stuck in 'running' or 'paused' status with no progress for X minutes and marks them as failed."""
    from datetime import timedelta
    from app.models.run import Run, RunStep
    from app.models.task import Task
    from app.services.agent_executor import create_audit_entry
    
    threshold_time = datetime.now(timezone.utc) - timedelta(minutes=settings.ORPHAN_RUN_TIMEOUT_MINUTES)
    
    # Fetch all running/paused runs
    stmt = select(Run).filter(Run.status.in_(["running", "paused"]))
    result = await db.execute(stmt)
    stuck_runs = result.scalars().all()
    
    reaped_count = 0
    for run in stuck_runs:
        # Check the latest step
        step_stmt = select(RunStep).filter(RunStep.run_id == run.id).order_by(RunStep.created_at.desc()).limit(1)
        step_result = await db.execute(step_stmt)
        latest_step = step_result.scalars().first()
        
        last_activity = latest_step.created_at if latest_step else run.started_at
        
        # Ensure last_activity is timezone-aware for comparison
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
            
        if last_activity < threshold_time:
            logger.warning(f"Reaper: Run {run.id} is stuck in {run.status} (last activity: {last_activity}). Marking as failed.")
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            db.add(run)
            
            # Fetch and update associated task
            task = await db.get(Task, run.task_id)
            if task and task.status in ["in_progress", "paused"]:
                task.status = "failed"
                task.locked_at = None
                db.add(task)
                
            await create_audit_entry(
                db,
                task.company_id if task else 1,
                "system",
                "RUN_ORPHAN_REAPED",
                {"run_id": run.id, "task_id": run.task_id, "last_activity": last_activity.isoformat()}
            )
            reaped_count += 1
            
    if reaped_count > 0:
        await db.commit()
        logger.info(f"Reaper: Successfully reaped {reaped_count} orphan runs.")
