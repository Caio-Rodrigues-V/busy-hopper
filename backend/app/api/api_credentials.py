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

import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class CredentialValidateRequest(BaseModel):
    provider: str
    api_key: str

async def validate_api_credential(provider: str, api_key: str):
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}]
        )
    elif provider == "openai":
        import httpx
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=10.0)
            if resp.status_code != 200:
                raise Exception(f"OpenAI API Error: {resp.text}")
    elif provider == "gemini":
        import httpx
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            resp = await client.post("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", headers=headers, json=payload, timeout=10.0)
            if resp.status_code != 200:
                raise Exception(f"Gemini API Error: {resp.text}")
    elif provider == "openrouter":
        import httpx
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": "meta-llama/llama-3-8b-instruct:free",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=10.0)
            if resp.status_code != 200:
                raise Exception(f"OpenRouter API Error: {resp.text}")
    elif provider == "aws_bedrock":
        import json
        import boto3
        import asyncio
        try:
            config = json.loads(api_key)
            aws_access_key_id = config.get("aws_access_key_id")
            aws_secret_access_key = config.get("aws_secret_access_key")
            aws_region = config.get("aws_region", "us-east-1")
        except Exception:
            raise Exception("Invalid Bedrock configuration format. Must be JSON.")
        
        if not aws_access_key_id or not aws_secret_access_key:
            raise Exception("AWS access key ID and secret access key are required.")

        def test():
            session = boto3.Session(
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=aws_region
            )
            # Check control plane first
            try:
                c = session.client('bedrock')
                c.list_foundation_models()
                return
            except Exception as e:
                if "AccessDenied" not in str(e):
                    raise e
            # If list_foundation_models is blocked, test converse with active models
            c_runtime = session.client('bedrock-runtime')
            models_to_try = [
                "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "anthropic.claude-3-5-haiku-20241022-v1:0",
                "anthropic.claude-3-5-sonnet-20240620-v1:0",
                "anthropic.claude-3-haiku-20240307-v1:0"
            ]
            
            last_err = None
            for model_id in models_to_try:
                try:
                    c_runtime.converse(
                        modelId=model_id,
                        messages=[{"role": "user", "content": [{"text": "ping"}]}],
                        inferenceConfig={"maxTokens": 1}
                    )
                    return
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if "ResourceNotFoundException" in err_str or "access denied" in err_str.lower() or "not authorized" in err_str.lower():
                        continue
                    else:
                        raise e
            if last_err:
                raise last_err

        await asyncio.to_thread(test)
    else:
        raise Exception(f"Validation not supported for provider '{provider}'")

@router.post("/validate")
async def validate_credentials_route(
    req: CredentialValidateRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        await validate_api_credential(req.provider, req.api_key)
        return {"valid": True}
    except Exception as e:
        logger.error(f"Credentials validation failed: {e}", exc_info=True)
        return {"valid": False, "error": str(e)}
