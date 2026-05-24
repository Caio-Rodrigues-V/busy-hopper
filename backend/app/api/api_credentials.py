from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.api_credential import ApiCredential
from app.schemas.api_credential import ApiCredentialCreate, ApiCredentialResponse
from app.core.security import encrypt_key
from app.services.agent_executor import create_audit_entry

router = APIRouter()

@router.get("/", response_model=List[ApiCredentialResponse])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(select(ApiCredential).filter(ApiCredential.company_id == company.id))
    return result.scalars().all()

@router.post("/", response_model=ApiCredentialResponse)
async def create_credential(
    cred_in: ApiCredentialCreate,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Check if a credential already exists for this provider in the company
    existing_query = select(ApiCredential).filter(
        ApiCredential.company_id == company.id,
        ApiCredential.provider == cred_in.provider
    )
    existing = (await db.execute(existing_query)).scalars().first()
    
    last4_str = cred_in.api_key[-4:] if len(cred_in.api_key) >= 4 else cred_in.api_key
    encrypted = encrypt_key(cred_in.api_key)

    if existing:
        existing.encrypted_key = encrypted
        existing.last4 = last4_str
        await db.commit()
        await db.refresh(existing)
        
        await create_audit_entry(
            db, company.id, f"user_{current_user.id}",
            "UPDATE_API_CREDENTIALS", {"provider": cred_in.provider}
        )
        return existing

    new_cred = ApiCredential(
        company_id=company.id,
        provider=cred_in.provider,
        encrypted_key=encrypted,
        last4=last4_str
    )
    db.add(new_cred)
    await db.commit()
    await db.refresh(new_cred)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_API_CREDENTIALS", {"provider": cred_in.provider}
    )
    return new_cred

@router.delete("/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    cred_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(ApiCredential).filter(ApiCredential.id == cred_id, ApiCredential.company_id == company.id))
    cred = res.scalars().first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
        
    await db.delete(cred)
    await db.commit()
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "DELETE_API_CREDENTIALS", {"provider": cred.provider}
    )
    return
