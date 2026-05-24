from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import os
import json
import time
from datetime import datetime
from typing import Optional

from app.core.deps import get_db, get_current_company, get_current_user
from app.models.user import User
from app.models.company import Company
from app.models.api_credential import ApiCredential
from app.core.security import encrypt_key, decrypt_key
from app.services.agent_executor import create_audit_entry
from app.services.websocket_manager import manager

router = APIRouter()

class MetaConfigSchema(BaseModel):
    access_token: str
    ad_account_id: str
    page_id: Optional[str] = ""
    pixel_id: Optional[str] = ""

class MetaCampaignSchema(BaseModel):
    campaign_name: str
    objective: str
    daily_budget_usd: float

@router.get("/config")
async def get_meta_config(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    # Find existing credential for provider meta_ads
    query = select(ApiCredential).filter(
        ApiCredential.company_id == company.id,
        ApiCredential.provider == "meta_ads"
    )
    cred = (await db.execute(query)).scalars().first()
    if not cred:
        return {"configured": False}
    
    try:
        decrypted = decrypt_key(cred.encrypted_key)
        config_data = json.loads(decrypted)
        return {
            "configured": True,
            "ad_account_id": config_data.get("ad_account_id"),
            "page_id": config_data.get("page_id"),
            "pixel_id": config_data.get("pixel_id"),
            "has_token": bool(config_data.get("access_token")),
            "last4": cred.last4
        }
    except Exception:
        # Fallback if the encrypted key was just a single text string (not JSON)
        return {
            "configured": True,
            "has_token": True,
            "ad_account_id": "Not Configured",
            "page_id": "",
            "pixel_id": "",
            "last4": cred.last4
        }

@router.post("/config")
async def save_meta_config(
    config_in: MetaConfigSchema,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Check if a credential already exists for this provider in the company
    existing_query = select(ApiCredential).filter(
        ApiCredential.company_id == company.id,
        ApiCredential.provider == "meta_ads"
    )
    existing = (await db.execute(existing_query)).scalars().first()
    
    config_json = json.dumps(config_in.model_dump())
    encrypted = encrypt_key(config_json)
    
    # Suffix logic
    token = config_in.access_token
    last4_str = token[-4:] if len(token) >= 4 else token

    if existing:
        existing.encrypted_key = encrypted
        existing.last4 = last4_str
        await db.commit()
        await db.refresh(existing)
        
        await create_audit_entry(
            db, company.id, f"user_{current_user.id}",
            "UPDATE_META_CONFIG", {"ad_account_id": config_in.ad_account_id}
        )
        return {"status": "success", "message": "Meta configuration updated."}

    new_cred = ApiCredential(
        company_id=company.id,
        provider="meta_ads",
        encrypted_key=encrypted,
        last4=last4_str
    )
    db.add(new_cred)
    await db.commit()
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_META_CONFIG", {"ad_account_id": config_in.ad_account_id}
    )
    return {"status": "success", "message": "Meta configuration created."}

@router.post("/campaign")
async def create_meta_campaign(
    campaign_in: MetaCampaignSchema,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Find existing credential for provider meta_ads
    query = select(ApiCredential).filter(
        ApiCredential.company_id == company.id,
        ApiCredential.provider == "meta_ads"
    )
    cred = (await db.execute(query)).scalars().first()
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta Ads integration is not configured. Please set up Access Token and Ad Account ID first."
        )
    
    try:
        decrypted = decrypt_key(cred.encrypted_key)
        config_data = json.loads(decrypted)
        ad_account_id = config_data.get("ad_account_id")
        page_id = config_data.get("page_id")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta Ads configuration is invalid or corrupted. Please re-configure."
        )

    # Perform Simulated Deploy
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    os.makedirs(workspace_dir, exist_ok=True)
    
    timestamp = int(time.time())
    filename = f"manual_meta_campaign_{timestamp}.json"
    target_path = os.path.join(workspace_dir, filename)
    
    campaign_id = f"act_{ad_account_id}/camp_{timestamp}"
    campaign_data = {
        "campaign_name": campaign_in.campaign_name,
        "objective": campaign_in.objective,
        "daily_budget_usd": campaign_in.daily_budget_usd,
        "status": "ACTIVE",
        "facebook_campaign_id": campaign_id,
        "deployed_at": datetime.utcnow().isoformat(),
        "ad_account_id": ad_account_id,
        "page_id": page_id,
        "mode": "MANUAL_DEPLOY"
    }
    
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(campaign_data, f, indent=2)
        
    # Create Audit log entry
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "DEPLOY_META_CAMPAIGN_MANUAL",
        {
            "campaign_name": campaign_in.campaign_name,
            "objective": campaign_in.objective,
            "daily_budget_usd": campaign_in.daily_budget_usd,
            "facebook_campaign_id": campaign_id
        }
    )
    
    # Broadcast status via websocket
    await manager.broadcast_to_company(company.id, {
        "type": "meta_campaign_deployed",
        "campaign_name": campaign_in.campaign_name,
        "facebook_campaign_id": campaign_id
    })
    
    return {
        "status": "success",
        "message": f"Simulated Meta campaign '{campaign_in.campaign_name}' deployed successfully.",
        "details": campaign_data
    }

@router.get("/campaigns")
async def list_meta_campaigns(
    company: Company = Depends(get_current_company)
):
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    if not os.path.exists(workspace_dir):
        return []
    
    campaigns = []
    for fname in os.listdir(workspace_dir):
        if fname.endswith(".json") and "meta_campaign" in fname:
            try:
                fpath = os.path.join(workspace_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Add filename reference
                    data["file_name"] = fname
                    campaigns.append(data)
            except Exception:
                pass
    
    # Sort by deployment date descending
    campaigns.sort(key=lambda x: x.get("deployed_at", ""), reverse=True)
    return campaigns
