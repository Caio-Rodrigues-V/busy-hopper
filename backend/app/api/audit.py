from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.deps import get_db, get_current_company
from app.models.company import Company
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse

router = APIRouter()

@router.get("/", response_model=List[AuditLogResponse])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(
        select(AuditLog)
        .filter(AuditLog.company_id == company.id)
        .order_by(AuditLog.created_at.desc())
    )
    return result.scalars().all()
