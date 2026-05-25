from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.services.agent_executor import create_audit_entry

router = APIRouter()

@router.get("/", response_model=List[CompanyResponse])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Company).filter(Company.user_id == current_user.id))
    return result.scalars().all()

@router.post("/", response_model=CompanyResponse)
async def create_company(
    company_in: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_company = Company(
        user_id=current_user.id,
        name=company_in.name,
        mission=company_in.mission,
        monthly_budget_usd=company_in.monthly_budget_usd,
        markup_pct=company_in.markup_pct
    )
    db.add(new_company)
    await db.commit()
    await db.refresh(new_company)
    
    # Register audit entry
    await create_audit_entry(
        db, new_company.id, f"user_{current_user.id}",
        "CREATE_COMPANY", {"name": new_company.name}
    )
    return new_company

@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Company).filter(Company.id == company_id, Company.user_id == current_user.id)
    )
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    company_in: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Company).filter(Company.id == company_id, Company.user_id == current_user.id)
    )
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    for field, val in company_in.model_dump(exclude_unset=True).items():
        setattr(company, field, val)
        
    await db.commit()
    await db.refresh(company)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "UPDATE_COMPANY_SETTINGS", company_in.model_dump(exclude_unset=True)
    )
    return company

@router.delete("/{company_id}")
async def delete_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Company).filter(Company.id == company_id, Company.user_id == current_user.id)
    )
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    await db.delete(company)
    await db.commit()
    
    # Register audit entry
    await create_audit_entry(
        db, company_id, f"user_{current_user.id}",
        "DELETE_COMPANY", {"name": company.name}
    )
    return {"status": "success", "message": f"Company {company.name} deleted successfully"}

