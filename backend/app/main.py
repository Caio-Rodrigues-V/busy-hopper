import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
from jose import jwt

from app.core.config import settings
from app.core.security import ALGORITHM
from app.services.websocket_manager import manager
from app.services.scheduler import start_scheduler, shutdown_scheduler

from app.api import auth, companies, api_credentials, agents, tasks, approvals, dashboard, audit, meta
from app.core.database import SessionLocal
from sqlalchemy.future import select
from app.models.company import Company

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
