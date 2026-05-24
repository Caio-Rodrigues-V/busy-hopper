import logging
import asyncio
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import SessionLocal
from app.models.agent import Agent
from app.models.task import Task
from app.services.agent_executor import AgentExecutor

logger = logging.getLogger(__name__)

async def check_pending_tasks():
    """Polls database for active agents with pending tasks and triggers execution."""
    async with SessionLocal() as db:
        try:
            # Query all tasks in 'todo' status that have an assignee agent that is active
            query = select(Task).join(Agent, Task.assignee_agent_id == Agent.id).filter(
                Task.status == "todo",
                Agent.status == "active",
                Task.locked_at.is_(None)
            )
            result = await db.execute(query)
            pending_tasks = result.scalars().all()

            for task in pending_tasks:
                logger.info(f"Scheduler: Triggering task {task.id} ('{task.title}') for Agent {task.assignee_agent_id}")
                # Spawn execution in a background task
                asyncio.create_task(run_agent_task(task.company_id, task.assignee_agent_id, task.id))
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
