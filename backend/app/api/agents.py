from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.models.run import Run, RunStep
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.services.agent_executor import create_audit_entry
from fastapi.responses import FileResponse
from datetime import datetime
import os

router = APIRouter()

@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(select(Agent).filter(Agent.company_id == company.id))
    return result.scalars().all()

@router.post("/", response_model=AgentResponse)
async def create_agent(
    agent_in: AgentCreate,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Verify boss reporting line validity
    if agent_in.boss_agent_id:
        boss = await db.get(Agent, agent_in.boss_agent_id)
        if not boss or boss.company_id != company.id:
            raise HTTPException(status_code=400, detail="Invalid boss agent (must belong to the same company).")

    new_agent = Agent(
        company_id=company.id,
        name=agent_in.name,
        title=agent_in.title,
        role_prompt=agent_in.role_prompt,
        boss_agent_id=agent_in.boss_agent_id,
        adapter_type=agent_in.adapter_type,
        model=agent_in.model,
        temperature=agent_in.temperature,
        tools=agent_in.tools,
        monthly_budget_usd=agent_in.monthly_budget_usd,
        status=agent_in.status,
        heartbeat_cron=agent_in.heartbeat_cron
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_AGENT", {"name": new_agent.name, "title": new_agent.title}
    )
    return new_agent

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    agent = await db.get(Agent, agent_id)
    if not agent or agent.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    agent_in: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    agent = await db.get(Agent, agent_id)
    if not agent or agent.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # Verify hierarchies
    if agent_in.boss_agent_id:
        if agent_in.boss_agent_id == agent.id:
            raise HTTPException(status_code=400, detail="An agent cannot report to themselves.")
        boss = await db.get(Agent, agent_in.boss_agent_id)
        if not boss or boss.company_id != company.id:
            raise HTTPException(status_code=400, detail="Invalid boss agent ID.")

    for field, val in agent_in.model_dump(exclude_unset=True).items():
        setattr(agent, field, val)
        
    await db.commit()
    await db.refresh(agent)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "UPDATE_AGENT", {"name": agent.name, "updates": agent_in.model_dump(exclude_unset=True)}
    )
    return agent

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    agent = await db.get(Agent, agent_id)
    if not agent or agent.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    await db.delete(agent)
    await db.commit()
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "DELETE_AGENT", {"name": agent.name}
    )
    return

@router.get("/{agent_id}/artifacts")
async def list_agent_artifacts(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    # 1. Verify agent ownership
    agent = await db.get(Agent, agent_id)
    if not agent or agent.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # 2. Get all run IDs of this agent
    runs_result = await db.execute(select(Run.id).filter(Run.agent_id == agent_id))
    run_ids = runs_result.scalars().all()
    
    if not run_ids:
        return []
        
    # 3. Get all run steps for these runs
    steps_result = await db.execute(
        select(RunStep).filter(RunStep.run_id.in_(run_ids))
    )
    steps = steps_result.scalars().all()
    
    # 4. Filter steps for artifact creation
    artifacts_map = {}
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    
    for step in steps:
        if step.kind == "tool_call" and step.input:
            tool_name = step.input.get("tool_name")
            tool_input = step.input.get("input", {})
            
            filename = None
            tool_type = None
            
            if tool_name == "read_write_file" and tool_input.get("action") == "write":
                filename = tool_input.get("filename")
                tool_type = "document"
            elif tool_name == "generate_image_asset":
                filename = tool_input.get("filename")
                if filename and not filename.lower().endswith(".svg"):
                    filename = os.path.splitext(filename)[0] + ".svg"
                tool_type = "image"
                
            if filename:
                clean_filename = os.path.basename(filename)
                fpath = os.path.join(workspace_dir, clean_filename)
                
                if os.path.exists(fpath):
                    stats = os.stat(fpath)
                    artifacts_map[clean_filename] = {
                        "filename": clean_filename,
                        "type": tool_type,
                        "size_bytes": stats.st_size,
                        "created_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        "prompt": tool_input.get("prompt", "")
                    }
                    
    # Sort by created_at descending
    sorted_artifacts = sorted(
        artifacts_map.values(),
        key=lambda x: x["created_at"],
        reverse=True
    )
    return sorted_artifacts

@router.get("/{agent_id}/artifacts/{filename}")
async def get_agent_artifact(
    agent_id: int,
    filename: str,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    # 1. Verify agent ownership
    agent = await db.get(Agent, agent_id)
    if not agent or agent.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # 2. Prevent directory traversal
    clean_filename = os.path.basename(filename)
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    target_path = os.path.abspath(os.path.join(workspace_dir, clean_filename))
    
    if not target_path.startswith(workspace_dir):
        raise HTTPException(status_code=403, detail="Access denied. Outside of authorized directory.")
        
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Artifact file not found.")
        
    # 3. Detect media type
    media_type = "application/octet-stream"
    if clean_filename.lower().endswith(".svg"):
        media_type = "image/svg+xml"
    elif clean_filename.lower().endswith(".txt") or clean_filename.lower().endswith(".md"):
        media_type = "text/plain; charset=utf-8"
    elif clean_filename.lower().endswith(".json"):
        media_type = "application/json"
        
    return FileResponse(target_path, media_type=media_type)
