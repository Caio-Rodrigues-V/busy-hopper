from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field
import os
import json
import time
import httpx
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
    daily_budget_usd: float = Field(gt=0)

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
        access_token = config_data.get("access_token")
        ad_account_id = config_data.get("ad_account_id")
        page_id = config_data.get("page_id", "")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta Ads configuration is invalid or corrupted. Please re-configure."
        )

    if not access_token or not ad_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta Access Token and Ad Account ID are required."
        )

    # Call Meta Graph API to actually create the campaign
    url = f"https://graph.facebook.com/v20.0/act_{ad_account_id}/campaigns"
    
    # Map objectives. Meta simplified objectives (v15+):
    # OUTCOMES, SALES, LEADS, TRAFFIC, AWARENESS, ENGAGEMENT, APP_PROMOTION
    objective_map = {
        "CONVERSIONS": "OUTCOMES",
        "LEAD_GENERATION": "OUTCOMES",
        "TRAFFIC": "TRAFFIC",
        "REACH": "AWARENESS"
    }
    meta_objective = objective_map.get(campaign_in.objective, campaign_in.objective)
    
    # Budget in cents
    budget_cents = int(campaign_in.daily_budget_usd * 100)
    
    payload = {
        "name": campaign_in.campaign_name,
        "objective": meta_objective,
        "status": "PAUSED", # Create as paused so they can activate it in Meta Ads Manager
        "daily_budget": budget_cents,
        "special_ad_categories": "[]", # Required field for Meta API
        "access_token": access_token
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, data=payload, timeout=15.0)
            if response.status_code != 200:
                try:
                    err_data = response.json()
                    err_msg = err_data.get("error", {}).get("message", "Unknown Meta API error")
                except Exception:
                    err_msg = response.text
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Meta Ads API Error: {err_msg}"
                )
            
            res_data = response.json()
            campaign_id = res_data.get("id")
            
            campaign_data = {
                "campaign_name": campaign_in.campaign_name,
                "objective": campaign_in.objective,
                "daily_budget_usd": campaign_in.daily_budget_usd,
                "status": "PAUSED",
                "facebook_campaign_id": campaign_id,
                "deployed_at": datetime.utcnow().isoformat(),
                "ad_account_id": ad_account_id,
                "page_id": page_id,
                "mode": "REAL_DEPLOY"
            }
            
            # Save local campaign trace
            workspace_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
            )
            os.makedirs(workspace_dir, exist_ok=True)
            timestamp = int(time.time())
            filename = f"meta_campaign_{timestamp}.json"
            target_path = os.path.join(workspace_dir, filename)
            
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(campaign_data, f, indent=2)
                
            await create_audit_entry(
                db, company.id, f"user_{current_user.id}",
                "DEPLOY_META_CAMPAIGN_REAL",
                {
                    "campaign_name": campaign_in.campaign_name,
                    "objective": campaign_in.objective,
                    "daily_budget_usd": campaign_in.daily_budget_usd,
                    "facebook_campaign_id": campaign_id
                }
            )
            
            await manager.broadcast_to_company(company.id, {
                "type": "meta_campaign_deployed",
                "campaign_name": campaign_in.campaign_name,
                "facebook_campaign_id": campaign_id
            })
            
            return {
                "status": "success",
                "message": f"Real Meta campaign '{campaign_in.campaign_name}' deployed successfully.",
                "details": campaign_data
            }
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Network error communicating with Meta API: {str(e)}"
            )

@router.get("/campaigns")
async def list_meta_campaigns(
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
        return []
        
    try:
        decrypted = decrypt_key(cred.encrypted_key)
        config_data = json.loads(decrypted)
        access_token = config_data.get("access_token")
        ad_account_id = config_data.get("ad_account_id")
    except Exception:
        return []
        
    if not access_token or not ad_account_id:
        return []

    # Call Meta Graph API
    url = f"https://graph.facebook.com/v20.0/act_{ad_account_id}/campaigns"
    params = {
        "fields": "name,objective,daily_budget,status,start_time,created_time,insights{spend,impressions,clicks,conversions,ctr,actions}",
        "access_token": access_token
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=12.0)
            if response.status_code != 200:
                return []
            
            data = response.json()
            raw_campaigns = data.get("data", [])
            
            campaigns = []
            for rc in raw_campaigns:
                # Extract insights
                insights_list = rc.get("insights", {}).get("data", [])
                insights = insights_list[0] if insights_list else {}
                
                # Daily budget is returned in cents by Meta API
                daily_budget = float(rc.get("daily_budget", 0)) / 100.0 if rc.get("daily_budget") else 0.0
                
                # Spend
                spend = float(insights.get("spend", 0.0))
                
                # CTR, Clicks, Impressions
                impressions = int(insights.get("impressions", 0))
                clicks = int(insights.get("clicks", 0))
                ctr = float(insights.get("ctr", 0.0)) if "ctr" in insights else (clicks / impressions * 100.0 if impressions > 0 else 0.0)
                
                # Conversions
                conversions = int(insights.get("conversions", 0))
                actions = insights.get("actions", [])
                if not conversions:
                    for action in actions:
                        if action.get("action_type") in ["conversion", "lead", "offsite_conversion.fb_pixel_lead", "purchase", "onsite_conversion.lead_grouped"]:
                            conversions += int(action.get("value", 0))
                
                # ROAS (value of conversions / spend)
                purchase_value = 0.0
                for action in actions:
                    if action.get("action_type") in ["purchase", "omni_purchase", "revenue"]:
                        purchase_value += float(action.get("value", 0.0))
                roas = purchase_value / spend if spend > 0 else 0.0
                
                # Health status
                rc_status = rc.get("status", "ACTIVE")
                if rc_status == "ACTIVE":
                    if roas >= 2.5:
                        health = "Excellent"
                    elif roas >= 1.5:
                        health = "Stable"
                    else:
                        health = "Underperforming"
                else:
                    health = "Paused"
                
                campaigns.append({
                    "campaign_name": rc.get("name"),
                    "objective": rc.get("objective"),
                    "daily_budget_usd": daily_budget,
                    "total_spent": spend,
                    "status": rc_status,
                    "facebook_campaign_id": rc.get("id"),
                    "deployed_at": rc.get("created_time") or rc.get("start_time") or datetime.utcnow().isoformat(),
                    "ad_account_id": ad_account_id,
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": ctr,
                    "conversions": conversions,
                    "roas": roas,
                    "health": health,
                    "mode": "REAL_DEPLOY"
                })
            return campaigns
        except Exception:
            return []
