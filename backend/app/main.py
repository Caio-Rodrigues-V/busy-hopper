import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import ALGORITHM
from app.services.websocket_manager import manager
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.core.deps import get_db

from app.api import auth, companies, api_credentials, agents, tasks, approvals, dashboard, audit, meta
from app.core.database import SessionLocal
from sqlalchemy.future import select
from app.models.company import Company
from app.core.logging_config import setup_logging

# Setup logger
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Run database migrations programmatically on startup
    try:
        logger.info("Running database migrations programmatically...")
        import os
        from alembic.config import Config
        from alembic import command
        import asyncio

        def run_migrations():
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ini_path = os.path.join(backend_dir, "alembic.ini")
            alembic_cfg = Config(ini_path)
            script_location = os.path.join(backend_dir, "alembic")
            alembic_cfg.set_main_option("script_location", script_location)
            alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
            command.upgrade(alembic_cfg, "head")

        await asyncio.to_thread(run_migrations)
        logger.info("Database migrations completed successfully.")
    except Exception as e:
        logger.error(f"Failed to run database migrations: {e}")

    # 2. Run database prepopulation/seeding programmatically
    if os.getenv("SEED_DATABASE") == "true":
        try:
            logger.info("Running database seeding programmatically...")
            from app.database_prepop import main as seed_db
            await seed_db()
            logger.info("Database seeding completed.")
        except Exception as e:
            logger.error(f"Failed to seed database: {e}")
    else:
        logger.info("Database seeding skipped (SEED_DATABASE env var is not set to 'true').")

    # 3. Run orphan runs reaper on boot
    try:
        logger.info("Running orphan runs reaper...")
        from app.services.scheduler import reap_orphan_runs
        async with SessionLocal() as db:
            await reap_orphan_runs(db)
    except Exception as e:
        logger.error(f"Failed to run orphan runs reaper: {e}")

    # Startup: Start APScheduler agent heartbeats
    start_scheduler()
    yield
    # Shutdown: Stop APScheduler
    shutdown_scheduler()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trust proxy headers for HTTPS redirects
@app.middleware("http")
async def forward_proto_middleware(request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# Register Endpoints
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(companies.router, prefix=f"{settings.API_V1_STR}/companies", tags=["companies"])
app.include_router(api_credentials.router, prefix=f"{settings.API_V1_STR}/credentials", tags=["credentials"])
app.include_router(agents.router, prefix=f"{settings.API_V1_STR}/agents", tags=["agents"])
app.include_router(tasks.router, prefix=f"{settings.API_V1_STR}/tasks", tags=["tasks"])
app.include_router(approvals.router, prefix=f"{settings.API_V1_STR}/approvals", tags=["approvals"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["dashboard"])
app.include_router(audit.router, prefix=f"{settings.API_V1_STR}/audit", tags=["audit"])
app.include_router(meta.router, prefix=f"{settings.API_V1_STR}/meta", tags=["meta"])

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # 1. Verify Database Connectivity
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check failed: database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is unavailable."
        )

    # 2. Verify Scheduler Heartbeats loop activity
    from app.services.scheduler import scheduler
    if not scheduler.running:
        logger.error("Health check failed: scheduler is not running.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running."
        )

    return {
        "status": "healthy",
        "database": "connected",
        "scheduler": "running"
    }

@app.websocket("/api/v1/ws/{company_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    company_id: int,
    token: Optional[str] = None
):
    """WebSocket streaming endpoint for real-time task board updates, isolated by company_id and authorized by JWT token."""
    # 1. Enforce Token Presence
    if not token:
        logger.error(f"WebSocket connection rejected: Missing token for company {company_id}")
        await websocket.accept()
        await websocket.close(code=1008) # Policy Violation
        return

    # 2. Verify Token Authenticity
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            logger.error("WebSocket connection rejected: Token payload is missing user ID")
            await websocket.accept()
            await websocket.close(code=1008)
            return
    except Exception as e:
        logger.error(f"WebSocket connection rejected: Token validation failed: {e}")
        await websocket.accept()
        await websocket.close(code=1008)
        return

    # 3. Verify Company Ownership (Tenant Isolation Check)
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(Company).filter(Company.id == company_id))
            company = result.scalars().first()
            if not company or company.user_id != int(user_id):
                logger.error(f"WebSocket connection rejected: User {user_id} does not own company {company_id}")
                await websocket.accept()
                await websocket.close(code=1008)
                return
    except Exception as e:
        logger.error(f"WebSocket connection rejected: Database check error: {e}")
        await websocket.accept()
        await websocket.close(code=1008)
        return

    # 4. Authenticated connection established
    await manager.connect(websocket, company_id)
    try:
        while True:
            # Maintain active heartbeat listen channel
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, company_id)
    except Exception as e:
        logger.error(f"WebSocket connection error for company {company_id}: {e}")
        manager.disconnect(websocket, company_id)
